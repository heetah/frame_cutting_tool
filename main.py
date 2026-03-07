import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import cv2
import os
import subprocess
import time
import shutil
from PIL import Image

# ================= 自定義：三星風格雙把手時間軸 =================
class DualTimelineSlider(tk.Canvas):
    def __init__(self, master, width=640, height=45, max_val=100.0, command=None, bg_color="#2B2B2B"):
        super().__init__(master, width=width, height=height, bg=bg_color, highlightthickness=0)
        self.width = width
        self.height = height
        self.max_val = max_val
        self.command = command 

        self.pad = 15 
        self.track_w = width - 2 * self.pad

        self.start_val = 0.0
        self.end_val = max_val
        self.active_handle = None 

        self.bind("<Button-1>", self.click)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.release)

        self.draw()

    def set_max(self, max_val):
        self.max_val = max_val
        self.start_val = 0.0
        self.end_val = min(2.0, max_val) 
        self.draw()

    def get_vals(self):
        return self.start_val, self.end_val

    def val_to_x(self, val):
        if self.max_val == 0: return self.pad
        return self.pad + (val / self.max_val) * self.track_w

    def x_to_val(self, x):
        x = max(self.pad, min(x, self.width - self.pad))
        return ((x - self.pad) / self.track_w) * self.max_val

    def draw(self):
        self.delete("all")
        x1 = self.val_to_x(self.start_val)
        x2 = self.val_to_x(self.end_val)

        self.create_rectangle(self.pad, 12, self.width-self.pad, self.height-12, fill="#404040", outline="", tags="track")
        self.create_rectangle(x1, 12, x2, self.height-12, fill="#3498DB", outline="", tags="sel")
        
        self.create_rectangle(x1-8, 5, x1, self.height-5, fill="#FFFFFF", outline="#202020", tags="handle")
        self.create_line(x1-4, 15, x1-4, self.height-15, fill="#808080", width=2) 

        self.create_rectangle(x2, 5, x2+8, self.height-5, fill="#FFFFFF", outline="#202020", tags="handle")
        self.create_line(x2+4, 15, x2+4, self.height-15, fill="#808080", width=2)

    def click(self, event):
        x = event.x
        x1 = self.val_to_x(self.start_val)
        x2 = self.val_to_x(self.end_val)
        
        dist_start = abs(x - x1)
        dist_end = abs(x - x2)
        
        if dist_start < dist_end and dist_start < 25:
            self.active_handle = 'start'
        elif dist_end < dist_start and dist_end < 25:
            self.active_handle = 'end'
        else:
            self.active_handle = None

    def drag(self, event):
        if not self.active_handle: return
        val = self.x_to_val(event.x)
        
        if self.active_handle == 'start':
            self.start_val = max(0.0, min(val, self.end_val - 0.1))
            if self.command: self.command('start', self.start_val)
        else:
            self.end_val = min(self.max_val, max(val, self.start_val + 0.1))
            if self.command: self.command('end', self.end_val)
            
        self.draw()

    def release(self, event):
        self.active_handle = None


# ================= 主程式 =================
ctk.set_appearance_mode("Dark") 
ctk.set_default_color_theme("blue")

class VideoExtractorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🚀 CV Project - Timeline Frame Extractor")
        self.geometry("950x800")
        
        self.video_path = None
        self.cap = None
        self.video_fps = 0
        self.duration = 0
        self.is_playing = False
        self.play_after_id = None
        
        # 新增：用於儲存多個區段的佇列
        self.segments_queue = []

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # === 左側控制面板 ===
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(8, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Extraction Settings", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # FPS 設定 (加上預設數值顯示，並綁定 command)
        self.fps_label = ctk.CTkLabel(self.sidebar_frame, text="Target FPS: 5")
        self.fps_label.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="w")
        self.fps_slider = ctk.CTkSlider(self.sidebar_frame, from_=1, to=30, number_of_steps=29, command=self.update_fps_label)
        self.fps_slider.set(5)
        self.fps_slider.grid(row=2, column=0, padx=20, pady=(0, 10))

        # 畫質設定 (加上預設數值顯示，並綁定 command)
        self.quality_label = ctk.CTkLabel(self.sidebar_frame, text="JPEG Quality: 2")
        self.quality_label.grid(row=3, column=0, padx=20, pady=(10, 0), sticky="w")
        self.quality_slider = ctk.CTkSlider(self.sidebar_frame, from_=1, to=31, number_of_steps=30, command=self.update_quality_label)
        self.quality_slider.set(2)
        self.quality_slider.grid(row=4, column=0, padx=20, pady=(0, 10))

        self.folder_label = ctk.CTkLabel(self.sidebar_frame, text="Output Directory:")
        self.folder_label.grid(row=5, column=0, padx=20, pady=(10, 0), sticky="w")
        self.folder_entry = ctk.CTkEntry(self.sidebar_frame, placeholder_text="extracted_dataset")
        self.folder_entry.insert(0, "extracted_dataset")
        self.folder_entry.grid(row=6, column=0, padx=20, pady=(0, 10), sticky="ew")

        # === 右側主要顯示區 ===
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.top_control_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.top_control_frame.grid(row=0, column=0, pady=(10, 5), sticky="ew")
        
        self.upload_btn = ctk.CTkButton(self.top_control_frame, text="📁 Load Video", command=self.load_video, width=120)
        self.upload_btn.grid(row=0, column=0, padx=10)

        self.info_label = ctk.CTkLabel(self.top_control_frame, text="No video loaded.", text_color="gray")
        self.info_label.grid(row=0, column=1, padx=10)

        self.preview_label = ctk.CTkLabel(self.main_frame, text="Preview", fg_color="black", width=640, height=360)
        self.preview_label.grid(row=1, column=0, pady=10)

        self.timeline = DualTimelineSlider(self.main_frame, width=640, max_val=0, command=self.on_timeline_slide)
        self.timeline.grid(row=2, column=0, pady=(10, 5))

        self.timeline_info_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.timeline_info_frame.grid(row=3, column=0, sticky="ew", padx=30)
        self.timeline_info_frame.grid_columnconfigure(1, weight=1)

        self.time_info_label = ctk.CTkLabel(self.timeline_info_frame, text="[ 0.00s  -  0.00s ]  Length: 0.00s", font=ctk.CTkFont(family="Consolas", size=14))
        self.time_info_label.grid(row=0, column=0, sticky="w")

        self.play_btn = ctk.CTkButton(self.timeline_info_frame, text="▶ Play", command=self.toggle_play, state="disabled", width=80, fg_color="#F39C12", hover_color="#D68910")
        self.play_btn.grid(row=0, column=2, sticky="e", padx=(0, 10))

        # 新增：加入暫存按鈕
        self.add_queue_btn = ctk.CTkButton(self.timeline_info_frame, text="➕ Add to Queue", command=self.add_to_queue, state="disabled", width=120, fg_color="#2980B9", hover_color="#1F618D")
        self.add_queue_btn.grid(row=0, column=3, sticky="e")

        # 新增：暫存清單顯示區
        self.queue_frame = ctk.CTkFrame(self.main_frame, fg_color="#333333")
        self.queue_frame.grid(row=4, column=0, sticky="ew", padx=30, pady=(15, 5))
        self.queue_frame.grid_columnconfigure(0, weight=1)

        self.queue_label = ctk.CTkLabel(self.queue_frame, text="Queued Segments: 0", font=ctk.CTkFont(weight="bold"))
        self.queue_label.grid(row=0, column=0, sticky="w", padx=10, pady=5)
        
        self.clear_queue_btn = ctk.CTkButton(self.queue_frame, text="🗑️ Clear Queue", command=self.clear_queue, state="disabled", width=100, fg_color="#C0392B", hover_color="#922B21")
        self.clear_queue_btn.grid(row=0, column=1, sticky="e", padx=10, pady=5)

        self.extract_btn = ctk.CTkButton(self.main_frame, text="🚀 Start FFmpeg Extraction", command=self.run_extraction, fg_color="green", hover_color="darkgreen", state="disabled", height=40)
        self.extract_btn.grid(row=5, column=0, pady=(15, 10))

    # ================= UI 更新邏輯 =================
    def update_fps_label(self, value):
        # 將浮點數轉為整數顯示
        self.fps_label.configure(text=f"Target FPS: {int(value)}")

    def update_quality_label(self, value):
        self.quality_label.configure(text=f"JPEG Quality: {int(value)}")
    # ================= 核心邏輯 =================
    def load_video(self):
        file_path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.avi *.mov")])
        if not file_path: return

        self.stop_playback()
        self.video_path = file_path
        self.cap = cv2.VideoCapture(self.video_path)
        
        self.video_fps = self.cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = total_frames / self.video_fps if self.video_fps > 0 else 0

        self.info_label.configure(text=f"Loaded: {os.path.basename(file_path)} | Length: {self.duration:.2f}s | FPS: {self.video_fps:.2f}", text_color="white")

        self.timeline.set_max(self.duration)
        self.clear_queue() # 載入新影片時清空暫存
        
        self.play_btn.configure(state="normal")
        self.add_queue_btn.configure(state="normal")
        self.extract_btn.configure(state="normal")

        self.update_clip_info()
        self.show_frame_at(0)

    def on_timeline_slide(self, handle_type, value):
        self.stop_playback()
        self.update_clip_info()
        self.show_frame_at(value) 

    def update_clip_info(self):
        start_sec, end_sec = self.timeline.get_vals()
        clip_duration = end_sec - start_sec
        self.time_info_label.configure(text=f"[ {start_sec:.2f}s  -  {end_sec:.2f}s ]  Length: {clip_duration:.2f}s")

    def show_frame_at(self, seconds):
        if not self.cap: return
        self.cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ret, frame = self.cap.read()
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(640, 360))
            self.preview_label.configure(image=ctk_img, text="")
            self.preview_label.image = ctk_img

    # ================= 區段暫存邏輯 =================
    def add_to_queue(self):
        start_sec, end_sec = self.timeline.get_vals()
        clip_duration = end_sec - start_sec
        if clip_duration <= 0: return

        self.segments_queue.append((start_sec, end_sec))
        self.update_queue_ui()
        
    def clear_queue(self):
        self.segments_queue.clear()
        self.update_queue_ui()

    def update_queue_ui(self):
        count = len(self.segments_queue)
        if count == 0:
            self.queue_label.configure(text="Queued Segments: 0")
            self.clear_queue_btn.configure(state="disabled")
            self.extract_btn.configure(text="🚀 Start FFmpeg Extraction")
        else:
            # 顯示最近加入的三筆，避免文字太長
            display_text = f"Queued Segments: {count}  |  "
            recent_segments = self.segments_queue[-3:]
            display_text += ", ".join([f"[{s:.1f}s-{e:.1f}s]" for s, e in recent_segments])
            if count > 3: display_text += " ..."
            
            self.queue_label.configure(text=display_text)
            self.clear_queue_btn.configure(state="normal")
            self.extract_btn.configure(text=f"🚀 Extract {count} Segments")

    # ================= 播放控制邏輯 =================
    def toggle_play(self):
        if self.is_playing:
            self.stop_playback()
        else:
            self.start_playback()

    def start_playback(self):
        if not self.cap: return
        self.is_playing = True
        self.play_btn.configure(text="⏸ Stop", fg_color="#E74C3C", hover_color="#C0392B")
        
        start_sec, _ = self.timeline.get_vals()
        self.cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000)
        self.play_loop()

    def stop_playback(self):
        self.is_playing = False
        if self.play_after_id:
            self.after_cancel(self.play_after_id)
            self.play_after_id = None
        self.play_btn.configure(text="▶ Play", fg_color="#F39C12", hover_color="#D68910")
        
        if self.cap:
            start_sec, _ = self.timeline.get_vals()
            self.show_frame_at(start_sec)

    def play_loop(self):
        if not self.is_playing: return
        
        _, end_sec = self.timeline.get_vals()
        current_sec = self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0

        if current_sec >= end_sec:
            self.stop_playback()
            return

        ret, frame = self.cap.read()
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(640, 360))
            self.preview_label.configure(image=ctk_img)
            self.preview_label.image = ctk_img
            
            delay = int(1000 / self.video_fps) if self.video_fps > 0 else 33
            self.play_after_id = self.after(delay, self.play_loop)
        else:
            self.stop_playback()

    # ================= 擷取邏輯 =================
    def run_extraction(self):
        self.stop_playback()
        
        # 決定要處理哪些區段：如果清單有東西就處理清單，否則處理當前時間軸
        segments_to_process = self.segments_queue if self.segments_queue else [self.timeline.get_vals()]
        
        output_folder = self.folder_entry.get()
        fps_to_save = int(self.fps_slider.get())
        quality = int(self.quality_slider.get())

        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path is None:
            messagebox.showerror("Error", "FFmpeg not found! Please check your installation.")
            return

        self.extract_btn.configure(text="Processing...", state="disabled")
        self.update() 

        try:
            start_time_total = time.time()
            total_new_files = 0
            
            # 依序處理每一個區段
            for idx, (start_sec, end_sec) in enumerate(segments_to_process):
                clip_duration = end_sec - start_sec
                if clip_duration <= 0: continue
                
                # 給予獨特的 Timestamp 避免檔名覆蓋，idx 確保同秒數執行不會撞名
                current_timestamp = int(time.time()) + idx 
                output_pattern = os.path.join(output_folder, f"clip_{current_timestamp}_frame_%05d.jpg")

                command = [
                    ffmpeg_path, '-y',
                    '-ss', str(start_sec),
                    '-t', str(clip_duration),
                    '-i', self.video_path,
                    '-vf', f'fps={fps_to_save}',
                    '-q:v', str(quality),
                    output_pattern
                ]

                subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
                
                # 計算這次迴圈產生的檔案數量
                new_files_count = len([f for f in os.listdir(output_folder) if f"clip_{current_timestamp}" in f])
                total_new_files += new_files_count

            end_time_total = time.time()
            messagebox.showinfo(
                "Success", 
                f"Batch Extraction successful!\n\n"
                f"Processed {len(segments_to_process)} segments.\n"
                f"Added {total_new_files} new frames to '{output_folder}'.\n"
                f"Time taken: {end_time_total - start_time_total:.2f}s"
            )
            
            # 處理成功後自動清空暫存清單
            self.clear_queue()
            
        except subprocess.CalledProcessError as e:
            messagebox.showerror("FFmpeg Error", f"An error occurred during extraction:\n{e.stderr}")
        
        finally:
            self.extract_btn.configure(text="🚀 Start FFmpeg Extraction", state="normal")

if __name__ == "__main__":
    app = VideoExtractorApp()
    app.mainloop()