import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import cv2
import os
import subprocess
import time
from PIL import Image

# ================= 自定義：三星風格雙把手時間軸 =================
class DualTimelineSlider(tk.Canvas):
    def __init__(self, master, width=640, height=45, max_val=100.0, command=None, bg_color="#2B2B2B"):
        super().__init__(master, width=width, height=height, bg=bg_color, highlightthickness=0)
        self.width = width
        self.height = height
        self.max_val = max_val
        self.command = command # 拖拉時觸發的回呼函數

        self.pad = 15 # 左右留白
        self.track_w = width - 2 * self.pad

        self.start_val = 0.0
        self.end_val = max_val

        self.active_handle = None # 目前按住的把手 ('start' 或 'end')

        # 綁定滑鼠事件
        self.bind("<Button-1>", self.click)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.release)

        self.draw()

    def set_max(self, max_val):
        self.max_val = max_val
        self.start_val = 0.0
        self.end_val = min(2.0, max_val) # 預設選取前 2 秒
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

        # 畫背景軌道 (未選取區域)
        self.create_rectangle(self.pad, 12, self.width-self.pad, self.height-12, fill="#404040", outline="", tags="track")
        
        # 畫選取區域 (高亮)
        self.create_rectangle(x1, 12, x2, self.height-12, fill="#3498DB", outline="", tags="sel")
        
        # 左側把手 (Start)
        self.create_rectangle(x1-8, 5, x1, self.height-5, fill="#FFFFFF", outline="#202020", tags="handle")
        self.create_line(x1-4, 15, x1-4, self.height-15, fill="#808080", width=2) # 把手上的防滑紋

        # 右側把手 (End)
        self.create_rectangle(x2, 5, x2+8, self.height-5, fill="#FFFFFF", outline="#202020", tags="handle")
        self.create_line(x2+4, 15, x2+4, self.height-15, fill="#808080", width=2)

    def click(self, event):
        x = event.x
        x1 = self.val_to_x(self.start_val)
        x2 = self.val_to_x(self.end_val)
        
        # 判斷點擊靠近哪個把手
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
        
        # 限制最小裁切長度為 0.1 秒，並防止左右把手交叉
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
ctk.set_appearance_mode("Dark") # 強制深色模式讓介面更像剪輯軟體
ctk.set_default_color_theme("blue")

class VideoExtractorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🚀 CV Project - Timeline Frame Extractor")
        self.geometry("950x760")
        
        self.video_path = None
        self.cap = None
        self.video_fps = 0
        self.duration = 0
        self.is_playing = False
        self.play_after_id = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # === 左側控制面板 ===
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(8, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Extraction Settings", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.fps_label = ctk.CTkLabel(self.sidebar_frame, text="Target FPS:")
        self.fps_label.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="w")
        self.fps_slider = ctk.CTkSlider(self.sidebar_frame, from_=1, to=30, number_of_steps=29)
        self.fps_slider.set(5)
        self.fps_slider.grid(row=2, column=0, padx=20, pady=(0, 10))

        self.quality_label = ctk.CTkLabel(self.sidebar_frame, text="JPEG Quality (1=Best, 31=Worst):")
        self.quality_label.grid(row=3, column=0, padx=20, pady=(10, 0), sticky="w")
        self.quality_slider = ctk.CTkSlider(self.sidebar_frame, from_=1, to=31, number_of_steps=30)
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

        # 影像預覽區塊
        self.preview_label = ctk.CTkLabel(self.main_frame, text="Preview", fg_color="black", width=640, height=360)
        self.preview_label.grid(row=1, column=0, pady=10)

        # --- 整合自定義時間軸 ---
        self.timeline = DualTimelineSlider(self.main_frame, width=640, max_val=0, command=self.on_timeline_slide)
        self.timeline.grid(row=2, column=0, pady=(10, 5))

        # 時間資訊與播放按鈕
        self.timeline_info_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.timeline_info_frame.grid(row=3, column=0, sticky="ew", padx=30)
        self.timeline_info_frame.grid_columnconfigure(1, weight=1)

        self.time_info_label = ctk.CTkLabel(self.timeline_info_frame, text="[ 0.00s  -  0.00s ]  Length: 0.00s", font=ctk.CTkFont(family="Consolas", size=14))
        self.time_info_label.grid(row=0, column=0, sticky="w")

        self.play_btn = ctk.CTkButton(self.timeline_info_frame, text="▶ Play", command=self.toggle_play, state="disabled", width=80, fg_color="#F39C12", hover_color="#D68910")
        self.play_btn.grid(row=0, column=2, sticky="e")

        self.extract_btn = ctk.CTkButton(self.main_frame, text="🚀 Start FFmpeg Extraction", command=self.run_extraction, fg_color="green", hover_color="darkgreen", state="disabled", height=40)
        self.extract_btn.grid(row=4, column=0, pady=(20, 10))

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

        # 初始化時間軸
        self.timeline.set_max(self.duration)
        
        self.play_btn.configure(state="normal")
        self.extract_btn.configure(state="normal")

        self.update_clip_info()
        self.show_frame_at(0)

    def on_timeline_slide(self, handle_type, value):
        self.stop_playback()
        self.update_clip_info()
        self.show_frame_at(value) # 拖動左邊就顯示左邊畫面，拖右邊就顯示右邊畫面

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
        
        # 暫停後畫面跳回 Start 位置
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
        start_sec, end_sec = self.timeline.get_vals()
        clip_duration = end_sec - start_sec
        
        output_folder = self.folder_entry.get()
        fps_to_save = int(self.fps_slider.get())
        quality = int(self.quality_slider.get())

        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        current_timestamp = int(time.time())
        output_pattern = os.path.join(output_folder, f"clip_{current_timestamp}_frame_%05d.jpg")

        command = [
            'ffmpeg', '-y',
            '-ss', str(start_sec),
            '-t', str(clip_duration),
            '-i', self.video_path,
            '-vf', f'fps={fps_to_save}',
            '-q:v', str(quality),
            output_pattern
        ]

        self.extract_btn.configure(text="Processing...", state="disabled")
        self.update() 

        try:
            start_time = time.time()
            subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
            end_time = time.time()
            
            new_files_count = len([f for f in os.listdir(output_folder) if f"clip_{current_timestamp}" in f])
            messagebox.showinfo("Success", f"Extraction successful!\n\nAdded {new_files_count} new frames to '{output_folder}'.\nTime taken: {end_time - start_time:.2f}s")
            
        except subprocess.CalledProcessError as e:
            messagebox.showerror("FFmpeg Error", f"An error occurred:\n{e.stderr}")
        
        finally:
            self.extract_btn.configure(text="🚀 Start FFmpeg Extraction", state="normal")

if __name__ == "__main__":
    app = VideoExtractorApp()
    app.mainloop()