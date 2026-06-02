import tkinter as tk
from tkinter import messagebox
import requests
from requests.auth import HTTPDigestAuth
import pandas as pd
from datetime import datetime
import json
import os
import time
import threading

from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

DEVICE_FILE = "devices.json"
LOG_FILE = "log.txt"

# ✅ YOUR DRIVE FOLDER ID
DRIVE_FOLDER_ID = "1mAU4Ug_4kKt7IvySuB1hKz4GyFATMsJ1"

# ==============================
# LOG
# ==============================
def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} - {msg}\n")

def update_status(msg):
    status_label.config(text="Status: " + msg)
    root.update()
    log(msg)

# ==============================
# GOOGLE DRIVE UPLOAD
# ==============================
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_to_drive(file_name, branch):
    try:
        update_status("Connecting to Google Drive...")

        SCOPES = ['https://www.googleapis.com/auth/drive']

        creds = Credentials.from_service_account_file(
            'credentials.json',
            scopes=SCOPES
        )

        service = build('drive', 'v3', credentials=creds)

        update_status(f"Checking folder: {branch}")

        # 🔍 Check if branch folder exists
        query = f"'{DRIVE_FOLDER_ID}' in parents and name='{branch}' and mimeType='application/vnd.google-apps.folder' and trashed=false"

        results = service.files().list(
    q=query,
    fields="files(id, name)",
    supportsAllDrives=True,
    includeItemsFromAllDrives=True
).execute()
        folders = results.get('files', [])

        if folders:
            folder_id = folders[0]['id']
            update_status(f"Using existing folder: {branch}")
        else:
            update_status(f"Creating folder: {branch}")

            file_metadata = {
                'name': branch,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [DRIVE_FOLDER_ID]
            }

            folder = service.files().create(
    body=file_metadata,
    fields='id',
    supportsAllDrives=True
).execute()
            folder_id = folder.get('id')

        # 🚀 Upload file
        update_status("Uploading file...")

        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }

        media = MediaFileUpload(file_name, resumable=True)

        service.files().create(
    body=file_metadata,
    media_body=media,
    fields='id',
    supportsAllDrives=True
).execute()

        update_status("✅ File uploaded successfully")

    except Exception as e:
        log("Drive Upload Error: " + str(e))
        update_status("❌ Upload failed")
# ==============================
# SAVE DEVICE
# ==============================
def save_device():
    data = {
        "device_ip": entry_ip.get(),
        "serial": entry_serial.get(),
        "username": entry_user.get(),
        "password": entry_pass.get(),
        "start_ip": entry_start_ip.get(),
        "end_ip": entry_end_ip.get(),
        "schedule_time": entry_time.get(),
        "branch": entry_branch.get()
    }

    with open(DEVICE_FILE, "w") as f:
        json.dump(data, f)

    update_status("Device saved")
    messagebox.showinfo("Saved", "Device Saved")

# ==============================
# FIND DEVICE
# ==============================
def find_device(device):

    # DIRECT IP
    if device.get("device_ip"):
        try:
            url = f"http://{device['device_ip']}/ISAPI/System/deviceInfo"
            res = requests.get(url, auth=HTTPDigestAuth(device["username"], device["password"]), timeout=3)
            if res.status_code == 200:
                return device["device_ip"]
        except:
            pass

    # LAST IP
    if device.get("last_ip"):
        try:
            url = f"http://{device['last_ip']}/ISAPI/System/deviceInfo"
            res = requests.get(url, auth=HTTPDigestAuth(device["username"], device["password"]), timeout=3)
            if res.status_code == 200:
                return device["last_ip"]
        except:
            pass

    # SCAN RANGE (same as before)
    for i in range(1, 255):
        ip = f"192.168.1.{i}"
        try:
            url = f"http://{ip}/ISAPI/System/deviceInfo"
            res = requests.get(url, auth=HTTPDigestAuth(device["username"], device["password"]), timeout=2)
            if res.status_code == 200:
                return ip
        except:
            continue

    return None

# ==============================
# FETCH DATA
# ==============================
def fetch_data(start_date_str=None, end_date_str=None):
    try:
        with open(DEVICE_FILE, "r") as f:
            device = json.load(f)

        update_status("Connecting...")

        ip = find_device(device)

        if not ip:
            update_status("Device not found")
            return False

        device["last_ip"] = ip
        with open(DEVICE_FILE, "w") as f:
            json.dump(device, f)

        update_status(f"Connected {ip}")

        all_records = []

        # Read from GUI entries if arguments are not provided (e.g. during scheduled execution)
        if not start_date_str or not end_date_str:
            try:
                start_date_str = entry_from.get().strip()
                end_date_str = entry_to.get().strip()
            except (NameError, AttributeError):
                # Fallback to May 2026 if GUI fields are not accessible
                start_date_str = "2026-05-01"
                end_date_str = "2026-05-31"

        start_time = f"{start_date_str}T00:00:00"
        end_time = f"{end_date_str}T23:59:59"

        update_status(f"Querying {start_date_str} to {end_date_str}...")
        position = 0

        while True:
            url = f"http://{ip}/ISAPI/AccessControl/AcsEvent?format=json"

            payload = {
                "AcsEventCond": {
                    "searchID": "1",
                    "searchResultPosition": position,
                    "maxResults": 30,
                    "major": 5,
                    "minor": 0,
                    "startTime": start_time,
                    "endTime": end_time
                }
            }

            res = requests.post(url, auth=HTTPDigestAuth(device["username"], device["password"]), json=payload, timeout=30)

            data = res.json()
            events = data.get("AcsEvent", {}).get("InfoList", [])

            if not events:
                break

            for e in events:
                if e.get("eventType") == 75 or "Face" in str(e):
                    all_records.append({
                        "Employee ID": e.get("employeeNoString", ""),
                        "Employee Name": e.get("name", ""),
                        "DateTime": e.get("time", "")
                    })

            position += len(events)
            update_status(f"Fetching {position}")

        if not all_records:
            update_status("No records found in date range")
            return True

        df = pd.DataFrame(all_records)

        df["DateTime"] = pd.to_datetime(df["DateTime"]).dt.tz_localize(None)
        df["Date"] = df["DateTime"].dt.date
        df["Time"] = df["DateTime"].dt.time

        final = []

        grouped = df.sort_values("DateTime").groupby(["Employee ID", "Employee Name", "Date"])

        for (emp, name, date), group in grouped:
            times = list(group["Time"])
            punch_list = ", ".join([t.strftime("%H:%M") for t in times])

            final.append({
                "Date": date,
                "Employee Name": name,
                "Employee ID": emp,
                "First In": times[0].strftime("%H:%M"),
                "Last Out": times[-1].strftime("%H:%M"),
                "Break Out": times[1].strftime("%H:%M") if len(times) > 2 else "",
                "Break In": times[-2].strftime("%H:%M") if len(times) > 3 else "",
                "Total Punches": punch_list
            })

        final_df = pd.DataFrame(final)

        # Generate filename with date range
        s_fn = start_date_str.replace("-", "")
        e_fn = end_date_str.replace("-", "")
        file_name = f"{device['branch']}_{s_fn}_to_{e_fn}.xlsx"
        
        final_df.to_excel(file_name, index=False)

        update_status("Excel file created")

        # Upload to Drive
        upload_to_drive(file_name, device["branch"])

        update_status("Process complete")
        return True

    except Exception as e:
        log(str(e))
        update_status("Error: " + str(e))
        return False

# ==============================
# MANUAL FETCH
# ==============================
def manual_fetch():
    from_date = entry_from.get().strip()
    to_date = entry_to.get().strip()
    
    try:
        # Simple format validation
        datetime.strptime(from_date, "%Y-%m-%d")
        datetime.strptime(to_date, "%Y-%m-%d")
    except ValueError:
        messagebox.showerror("Invalid Date Format", "Please enter dates in YYYY-MM-DD format.")
        return
        
    # Start fetch in background thread to prevent UI freezing
    threading.Thread(target=fetch_data, args=(from_date, to_date), daemon=True).start()

# ==============================
# SCHEDULER
# ==============================
def scheduler():
    while True:
        try:
            with open(DEVICE_FILE, "r") as f:
                device = json.load(f)

            now = datetime.now().strftime("%H:%M")

            if now == device["schedule_time"]:
                update_status("Scheduled run started")

                # Scheduled run uses dates from entry boxes or defaults
                success = fetch_data()

                while not success:
                    update_status("Retry in 5 min...")
                    time.sleep(300)
                    success = fetch_data()

                time.sleep(60)

            time.sleep(30)

        except:
            time.sleep(60)

def start_scheduler():
    threading.Thread(target=scheduler, daemon=True).start()
    update_status("Scheduler started")

# ==============================
# UI
# ==============================
root = tk.Tk()
root.title("Smart Attendance System")
root.geometry("680x680")

# Palette
BG_COLOR = "#181825"
CARD_BG = "#1e1e2e"
TEXT_COLOR = "#cdd6f4"
SUB_TEXT = "#a6adc8"
ENTRY_BG = "#313244"
ENTRY_FG = "#cdd6f4"
ACCENT_BLUE = "#89b4fa"
ACCENT_GREEN = "#a6e3a1"
ACCENT_PEACH = "#fab387"
ACCENT_RED = "#f38ba8"

root.configure(bg=BG_COLOR)

# Custom Widget Helpers
def create_label(parent, text, font=("Segoe UI", 10, "bold"), fg=SUB_TEXT, bg=CARD_BG):
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg)

def create_entry(parent, width=25):
    entry = tk.Entry(parent, font=("Segoe UI", 10), bg=ENTRY_BG, fg=ENTRY_FG, 
                     insertbackground=TEXT_COLOR, relief="flat", bd=2, 
                     highlightthickness=1, highlightbackground="#45475a",
                     highlightcolor=ACCENT_BLUE, width=width)
    return entry

def create_button(parent, text, command, bg_color, hover_color, fg_color="#11111b", width=18):
    btn = tk.Button(parent, text=text, command=command, font=("Segoe UI", 10, "bold"),
                    bg=bg_color, fg=fg_color, activebackground=hover_color,
                    activeforeground=fg_color, relief="flat", bd=0, cursor="hand2",
                    padx=10, pady=6, width=width)
    btn.bind("<Enter>", lambda e: btn.config(bg=hover_color))
    btn.bind("<Leave>", lambda e: btn.config(bg=bg_color))
    return btn

# Header Banner
header_frame = tk.Frame(root, bg=CARD_BG, height=70)
header_frame.pack(fill="x", side="top")
header_frame.pack_propagate(False)

header_title = tk.Label(header_frame, text="SMART ATTENDANCE DASHBOARD", font=("Segoe UI", 16, "bold"), fg=ACCENT_BLUE, bg=CARD_BG)
header_title.pack(anchor="center", pady=(10, 2))
header_sub = tk.Label(header_frame, text="Biometric Event Fetcher & Drive Sync Utility", font=("Segoe UI", 9, "italic"), fg=SUB_TEXT, bg=CARD_BG)
header_sub.pack(anchor="center")

# Main Container with two columns
main_container = tk.Frame(root, bg=BG_COLOR)
main_container.pack(fill="both", expand=True, padx=20, pady=15)

# LEFT COLUMN: Device Configuration
left_frame = tk.LabelFrame(main_container, text=" Device Settings ", font=("Segoe UI", 11, "bold"), bg=CARD_BG, fg=ACCENT_BLUE, bd=1, relief="solid", labelanchor="nw")
left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

# Inner padding frame for aesthetics
left_inner = tk.Frame(left_frame, bg=CARD_BG)
left_inner.pack(padx=15, pady=15, fill="both", expand=True)

# Device Configuration Inputs
create_label(left_inner, "Device IP").pack(anchor="w", pady=(0, 2))
entry_ip = create_entry(left_inner)
entry_ip.pack(fill="x", pady=(0, 12))

create_label(left_inner, "Serial Number").pack(anchor="w", pady=(0, 2))
entry_serial = create_entry(left_inner)
entry_serial.pack(fill="x", pady=(0, 12))

create_label(left_inner, "Username").pack(anchor="w", pady=(0, 2))
entry_user = create_entry(left_inner)
entry_user.pack(fill="x", pady=(0, 12))

create_label(left_inner, "Password").pack(anchor="w", pady=(0, 2))
entry_pass = create_entry(left_inner)
entry_pass.config(show="*")
entry_pass.pack(fill="x", pady=(0, 12))

create_label(left_inner, "Branch Name").pack(anchor="w", pady=(0, 2))
entry_branch = create_entry(left_inner)
entry_branch.pack(fill="x", pady=(0, 5))


# RIGHT COLUMN: Scheduler, Scanner & Date Options
right_container = tk.Frame(main_container, bg=BG_COLOR)
right_container.pack(side="right", fill="both", expand=True, padx=(10, 0))

# Date Frame
date_frame = tk.LabelFrame(right_container, text=" Attendance Date Range ", font=("Segoe UI", 11, "bold"), bg=CARD_BG, fg=ACCENT_PEACH, bd=1, relief="solid")
date_frame.pack(fill="x", pady=(0, 10))

date_inner = tk.Frame(date_frame, bg=CARD_BG)
date_inner.pack(padx=15, pady=12, fill="x")

create_label(date_inner, "From Date (YYYY-MM-DD)").pack(anchor="w", pady=(0, 2))
entry_from = create_entry(date_inner)
entry_from.pack(fill="x", pady=(0, 10))
# Default to May Month
entry_from.insert(0, "2026-05-01")

create_label(date_inner, "To Date (YYYY-MM-DD)").pack(anchor="w", pady=(0, 2))
entry_to = create_entry(date_inner)
entry_to.pack(fill="x")
# Default to May Month
entry_to.insert(0, "2026-05-31")

# Scheduler Frame
scheduler_frame = tk.LabelFrame(right_container, text=" Scheduler Settings ", font=("Segoe UI", 11, "bold"), bg=CARD_BG, fg=ACCENT_GREEN, bd=1, relief="solid")
scheduler_frame.pack(fill="x", pady=(0, 10))

sched_inner = tk.Frame(scheduler_frame, bg=CARD_BG)
sched_inner.pack(padx=15, pady=12, fill="x")

create_label(sched_inner, "Schedule Time (HH:MM)").pack(anchor="w", pady=(0, 2))
entry_time = create_entry(sched_inner)
entry_time.pack(fill="x")

# Scanner Frame
scanner_frame = tk.LabelFrame(right_container, text=" Network IP Scanner ", font=("Segoe UI", 11, "bold"), bg=CARD_BG, fg=SUB_TEXT, bd=1, relief="solid")
scanner_frame.pack(fill="x")

scan_inner = tk.Frame(scanner_frame, bg=CARD_BG)
scan_inner.pack(padx=15, pady=12, fill="x")

create_label(scan_inner, "Start IP").pack(anchor="w", pady=(0, 2))
entry_start_ip = create_entry(scan_inner)
entry_start_ip.pack(fill="x", pady=(0, 10))

create_label(scan_inner, "End IP").pack(anchor="w", pady=(0, 2))
entry_end_ip = create_entry(scan_inner)
entry_end_ip.pack(fill="x")


# Actions Panel (Save, Fetch, Schedule Buttons)
action_frame = tk.Frame(root, bg=CARD_BG, bd=1, relief="solid")
action_frame.pack(fill="x", side="top", padx=20, pady=(0, 15))

# Center the buttons inside action_frame
btn_save = create_button(action_frame, "Save Device", save_device, ACCENT_PEACH, "#e0a16c")
btn_save.pack(side="left", padx=20, pady=15, expand=True)

btn_fetch = create_button(action_frame, "Fetch Now", manual_fetch, ACCENT_BLUE, "#739bcf")
btn_fetch.pack(side="left", padx=20, pady=15, expand=True)

btn_sched = create_button(action_frame, "Start Scheduler", start_scheduler, ACCENT_GREEN, "#8ccb87")
btn_sched.pack(side="left", padx=20, pady=15, expand=True)


# Status Bar
status_frame = tk.Frame(root, bg="#11111b", height=30)
status_frame.pack(fill="x", side="bottom")
status_frame.pack_propagate(False)

status_label = tk.Label(status_frame, text="Status: Ready", font=("Segoe UI", 9, "bold"), fg=ACCENT_BLUE, bg="#11111b")
status_label.pack(side="left", padx=15)


# Load Saved Configuration
def load_device():
    if os.path.exists(DEVICE_FILE):
        try:
            with open(DEVICE_FILE, "r") as f:
                data = json.load(f)
            
            # Clear default entries if loaded
            if data.get("device_ip"):
                entry_ip.delete(0, tk.END)
                entry_ip.insert(0, data["device_ip"])
            if data.get("serial"):
                entry_serial.delete(0, tk.END)
                entry_serial.insert(0, data["serial"])
            if data.get("username"):
                entry_user.delete(0, tk.END)
                entry_user.insert(0, data["username"])
            if data.get("password"):
                entry_pass.delete(0, tk.END)
                entry_pass.insert(0, data["password"])
            if data.get("start_ip"):
                entry_start_ip.delete(0, tk.END)
                entry_start_ip.insert(0, data["start_ip"])
            if data.get("end_ip"):
                entry_end_ip.delete(0, tk.END)
                entry_end_ip.insert(0, data["end_ip"])
            if data.get("schedule_time"):
                entry_time.delete(0, tk.END)
                entry_time.insert(0, data["schedule_time"])
            if data.get("branch"):
                entry_branch.delete(0, tk.END)
                entry_branch.insert(0, data["branch"])
        except Exception as e:
            log("Load Error: " + str(e))

load_device()

root.mainloop()