import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import threading
import os
import subprocess
import yt_dlp

class YouTubeDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Downloader - Tải video YouTube")
        self.root.geometry("870x520")

        self.urls = []
        self.folder_var = tk.StringVar()
        self.quality_var = tk.StringVar(value="480p")
        self.mode_var = tk.StringVar(value="video")

        self.active_downloads = {}

        self.create_widgets()

    def create_widgets(self):
        tk.Label(self.root, text="URL YouTube (mỗi dòng 1 link):").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        self.url_text = tk.Text(self.root, height=5, width=100)
        self.url_text.grid(row=1, column=0, columnspan=7, padx=10)

        # RadioButton chọn chế độ tải
        tk.Label(self.root, text="Chế độ:").grid(row=2, column=0, sticky='w', padx=10)
        tk.Radiobutton(self.root, text="Video", variable=self.mode_var, value="video").grid(row=2, column=0)
        tk.Radiobutton(self.root, text="Playlist", variable=self.mode_var, value="playlist").grid(row=2, column=1, columnspan=10, sticky='w')

        tk.Label(self.root, text="Thư mục lưu:").grid(row=3, column=0, sticky='w', padx=10)
        tk.Entry(self.root, textvariable=self.folder_var, width=65).grid(row=3, column=0, columnspan=4, pady=5)
        tk.Button(self.root, text="Chọn", command=self.choose_folder).grid(row=3, column=3)
        tk.Label(self.root, text="Chất lượng:").grid(row=4, column=0, sticky='w', padx=10)
        ttk.Combobox(self.root, textvariable=self.quality_var, values=["480p", "720p", "1080p", "mp3"]).grid(row=4, column=0, columnspan=2)

        

        columns = ("ID", "Tiêu đề", "Thời lượng", "Trạng thái", "Tiến độ", "Kích thước")
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings")
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=140)
        self.tree.grid(row=6, column=0, columnspan=7, padx=10, pady=10)
        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)

        btn_frame = tk.Frame(self.root)
        btn_frame.grid(row=7, column=0, columnspan=7, pady=10)
        tk.Button(btn_frame, text="Phân tích", command=self.analyze).grid(row=0, column=0, padx=5)
        tk.Button(btn_frame, text="Tải xuống", command=self.download_thread).grid(row=0, column=1, padx=5)
        tk.Button(btn_frame, text="Tải lại", command=self.retry_all).grid(row=0, column=4, padx=5)
        tk.Button(btn_frame, text="Xoá danh sách", command=self.clear_list).grid(row=0, column=5, padx=5)

        self.status_label = tk.Label(self.root, text="Sẵn sàng", anchor="w")
        self.status_label.grid(row=8, column=0, columnspan=7, sticky="we", padx=10)

    def choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_var.set(folder)

    def analyze(self):
        self.clear_list()
        raw_urls = self.url_text.get("1.0", tk.END).strip().splitlines()
        self.urls = [url.strip() for url in raw_urls if url.strip()]

        for url in self.urls:
            info = self.get_video_info(url)
            if info:
                vid = info.get("id", url)
                title = info.get("title", "Không rõ")
                duration = self.format_duration(info.get("duration", 0))
                self.tree.insert('', 'end', iid=vid, values=(vid, title, duration, "Chờ tải", "0%", "--"))

    def get_video_info(self, url):
        try:
            ydl_opts = {'quiet': True, 'skip_download': True, 'extract_flat': 'in_playlist' if self.mode_var.get() == 'playlist' else False}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info if self.mode_var.get() == 'video' else None
        except Exception as e:
            self.tree.insert('', 'end', values=("Lỗi", url, "", f"Lỗi phân tích: {str(e)}", "", ""))
            return None

    def format_duration(self, seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def download_thread(self):
        threading.Thread(target=self.download_all, daemon=True).start()

    def download_all(self):
        folder = self.folder_var.get()
        quality = self.quality_var.get()

        if not folder:
            messagebox.showwarning("Thiếu thư mục", "Vui lòng chọn thư mục lưu video.")
            return

        for item in self.tree.get_children():
            video_id = self.tree.item(item)['values'][0]
            url = next((u for u in self.urls if video_id in u or u.endswith(video_id)), None)
            if not url:
                continue
            self.update_status(video_id, "Đang tải")

            if quality == "mp3":
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(folder, '%(title)s.%(ext)s'),
                    'progress_hooks': [self.create_hook(video_id)],
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                }
            else:
                ydl_opts = {
                    'format': f'bestvideo[height<={quality[:-1]}]+bestaudio/best',
                    'outtmpl': os.path.join(folder, '%(title)s.%(ext)s'),
                    'progress_hooks': [self.create_hook(video_id)],
                }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                self.update_status(video_id, "Hoàn tất")
            except Exception as e:
                self.update_status(video_id, f"Lỗi: {str(e)}")

    def create_hook(self, video_id):
        def hook(d):
            if d['status'] == 'downloading':
                percent = d.get('_percent_str', '').strip()
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
                if total_bytes:
                    size = round(total_bytes / (1024 * 1024), 2)
                    self.tree.set(video_id, "Tiến độ", percent)
                    self.tree.set(video_id, "Kích thước", f"{size} MB")
            elif d['status'] == 'finished':
                self.tree.set(video_id, "Tiến độ", "100%")
        return hook

    def update_status(self, video_id, status):
        if self.tree.exists(video_id):
            self.tree.set(video_id, "Trạng thái", status)

    def retry_all(self):
        self.download_thread()

    def clear_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.status_label.config(text="Sẵn sàng")

    def on_tree_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            confirm = messagebox.askyesno("Xoá", f"Bạn có muốn xoá video ID {item} khỏi danh sách?")
            if confirm:
                self.tree.delete(item)

if __name__ == "__main__":
    root = tk.Tk()
    app = YouTubeDownloaderApp(root)
    root.mainloop()
