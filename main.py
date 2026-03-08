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
        self.base_width = width
        self.width = width
        self.height = height
        self.max_val = max_val
        self.command = command 

        self.pad = 15 
        self.track_w = width - 2 * self.pad

        self.start_val = 0.0
        self.end_val = max_val
        self.active_handle = None 
        
        # 縮放比例紀錄
        self.zoom_level = 1.0

        self.bind("<Button-1>", self.click)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.release)
        
        # 綁定 Ctrl+滾輪 縮放 (兼容 Windows/Mac 及 Linux)
        self.bind("<Control-MouseWheel>", self.on_zoom)
        self.bind("<Control-Button-4>", self.on_zoom)
        self.bind("<Control-Button-5>", self.on_zoom)

        self.draw()

    def on_zoom(self, event):
        if self.max_val == 0: return # 沒有載入影片時不縮放

        # 判斷滾輪方向
        direction = 0
        if hasattr(event, "delta") and event.delta != 0:
            direction = 1 if event.delta > 0 else -1
        elif hasattr(event, "num"):
            direction = 1 if event.num == 4 else -1

        if direction > 0:
            self.zoom_level *= 1.25  # 放大
        elif direction < 0:
            self.zoom_level /= 1.25  # 縮小
            
        # 限制縮放範圍 (1x 到 20x)
        self.zoom_level = max(1.0, min(self.zoom_level, 20.0))
        
        # 更新寬度與重繪
        self.width = int(self.base_width * self.zoom_level)
        self.config(width=self.width)
        self.track_w = self.width - 2 * self.pad
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
        self.geometry("950x850")
        
        self.video_path = None
        self.cap = None
        self.video_fps = 0
        self.duration = 0
        self.is_playing = False
        self.play_after_id = None
        
        self.segments_queue = []
        self.preview_scale = 1.0  # 影片預覽縮放比例
        self.current_sec = 0.0    # 紀錄當前播放時間以利縮放重繪

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # === 左側控制面板 ===
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(8, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Extraction Settings", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.fps_label = ctk.CTkLabel(self.sidebar_frame, text="Target FPS: 5")
        self.fps_label.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="w")
        self.fps_slider = ctk.CTkSlider(self.sidebar_frame, from_=1, to=30, number_of_steps=29, command=self.update_fps_label)
        self.fps_slider.set(5)
        self.fps_slider.grid(row=2, column=0, padx=20, pady=(0, 10))

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

        # 改用可滾動框架包裝預覽區域
        self.preview_scroll_frame = ctk.CTkScrollableFrame(self.main_frame, width=640, height=360)
        self.preview_scroll_frame.grid(row=1, column=0, pady=10)
        self.preview_scroll_frame.grid_rowconfigure(0, weight=1)
        self.preview_scroll_frame.grid_columnconfigure(0, weight=1)
        
        self.preview_label = ctk.CTkLabel(self.preview_scroll_frame, text="Preview", fg_color="black")
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        # 影片預覽區域綁定 Ctrl+滾輪
        self._bind_video_zoom(self.preview_label)
        self._bind_video_zoom(self.preview_scroll_frame._parent_canvas) # 綁定背景Canvas確保隨處可觸發

        # 改用可滾動框架包裝時間軸 (為了支持寬度縮放)
        self.timeline_scroll_frame = ctk.CTkScrollableFrame(self.main_frame, width=640, height=65, orientation="horizontal")
        self.timeline_scroll_frame.grid(row=2, column=0, pady=(10, 5))
        
        self.timeline = DualTimelineSlider(self.timeline_scroll_frame, width=640, max_val=0, command=self.on_timeline_slide)
        self.timeline.grid(row=0, column=0)

        self.timeline_info_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.timeline_info_frame.grid(row=3, column=0, sticky="ew", padx=30)
        self.timeline_info_frame.grid_columnconfigure(1, weight=1)

        self.time_info_label = ctk.CTkLabel(self.timeline_info_frame, text="[ 0.00s  -  0.00s ]  Length: 0.00s", font=ctk.CTkFont(family="Consolas", size=14))
        self.time_info_label.grid(row=0, column=0, sticky="w")

        self.play_btn = ctk.CTkButton(self.timeline_info_frame, text="▶ Play", command=self.toggle_play, state="disabled", width=80, fg_color="#F39C12", hover_color="#D68910")
        self.play_btn.grid(row=0, column=2, sticky="e", padx=(0, 10))

        self.add_queue_btn = ctk.CTkButton(self.timeline_info_frame, text="➕ Add to Queue", command=self.add_to_queue, state="disabled", width=120, fg_color="#2980B9", hover_color="#1F618D")
        self.add_queue_btn.grid(row=0, column=3, sticky="e")

        self.queue_frame = ctk.CTkFrame(self.main_frame, fg_color="#333333")
        self.queue_frame.grid(row=4, column=0, sticky="ew", padx=30, pady=(15, 5))
        self.queue_frame.grid_columnconfigure(0, weight=1)

        self.queue_label = ctk.CTkLabel(self.queue_frame, text="Queued Segments: 0", font=ctk.CTkFont(weight="bold"))
        self.queue_label.grid(row=0, column=0, sticky="w", padx=10, pady=5)
        
        self.clear_queue_btn = ctk.CTkButton(self.queue_frame, text="🗑️ Clear Queue", command=self.clear_queue, state="disabled", width=100, fg_color="#C0392B", hover_color="#922B21")
        self.clear_queue_btn.grid(row=0, column=1, sticky="e", padx=10, pady=5)

        self.extract_btn = ctk.CTkButton(self.main_frame, text="🚀 Start FFmpeg Extraction", command=self.run_extraction, fg_color="green", hover_color="darkgreen", state="disabled", height=40)
        self.extract_btn.grid(row=5, column=0, pady=(15, 10))

    # ================= 綁定輔助方法 =================
    def _bind_video_zoom(self, widget):
        widget.bind("<Control-MouseWheel>", self.on_video_zoom)
        widget.bind("<Control-Button-4>", self.on_video_zoom)
        widget.bind("<Control-Button-5>", self.on_video_zoom)

    # ================= 影片預覽縮放邏輯 =================
    def on_video_zoom(self, event):
        if not self.cap: return
        
        direction = 0
        if hasattr(event, "delta") and event.delta != 0:
            direction = 1 if event.delta > 0 else -1
        elif hasattr(event, "num"):
            direction = 1 if event.num == 4 else -1

        if direction > 0:
            self.preview_scale *= 1.2
        elif direction < 0:
            self.preview_scale /= 1.2
            
        self.preview_scale = max(0.5, min(self.preview_scale, 8.0)) # 限制縮放比例
        self.show_frame_at(self.current_sec) # 原地重繪當下影格

    # ================= UI 更新邏輯 =================
    def update_fps_label(self, value):
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

        # 重置縮放
        self.preview_scale = 1.0
        self.timeline.zoom_level = 1.0
        self.timeline.set_max(self.duration)
        
        self.clear_queue() 
        
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

    def render_image(self, frame):
        # 負責將 cv2 畫面加上縮放比例並渲染至 UI
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        
        new_w = int(640 * self.preview_scale)
        new_h = int(360 * self.preview_scale)
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(new_w, new_h))
        
        self.preview_label.configure(image=ctk_img, text="")
        self.preview_label.image = ctk_img

    def show_frame_at(self, seconds):
        if not self.cap: return
        self.current_sec = seconds
        self.cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ret, frame = self.cap.read()
        if ret:
            self.render_image(frame)

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
        self.current_sec = self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0

        if self.current_sec >= end_sec:
            self.stop_playback()
            return

        ret, frame = self.cap.read()
        if ret:
            self.render_image(frame)
            delay = int(1000 / self.video_fps) if self.video_fps > 0 else 33
            self.play_after_id = self.after(delay, self.play_loop)
        else:
            self.stop_playback()

    # ================= 擷取邏輯 =================
    def run_extraction(self):
        self.stop_playback()
        
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
            
            for idx, (start_sec, end_sec) in enumerate(segments_to_process):
                clip_duration = end_sec - start_sec
                if clip_duration <= 0: continue
                
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
            
            self.clear_queue()
            
        except subprocess.CalledProcessError as e:
            messagebox.showerror("FFmpeg Error", f"An error occurred during extraction:\n{e.stderr}")
        
        finally:
            self.extract_btn.configure(text="🚀 Start FFmpeg Extraction", state="normal")

if __name__ == "__main__":
    app = VideoExtractorApp()
    app.mainloop()