import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import threading
import os
import re
import time
import logging
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
import yt_dlp
import webbrowser
from functools import partial


@dataclass
class VideoInfo:
    """Data class for video information"""
    id: str
    title: str
    duration: str
    url: str
    status: str = "Chờ tải"
    progress: str = "0%"
    size: str = "--"


class ProgressTracker:
    """Handles progress tracking for multiple downloads"""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.total_bytes = 0
        self.total_bytes_downloaded = 0
        self.bytes_downloaded_map: Dict[str, int] = {}
        self.total_bytes_map: Dict[str, int] = {}
    
    def reset(self):
        """Reset all progress tracking variables"""
        with self.lock:
            self.total_bytes = 0
            self.total_bytes_downloaded = 0
            self.bytes_downloaded_map.clear()
            self.total_bytes_map.clear()
    
    def update_progress(self, video_id: str, downloaded: int, total: int) -> float:
        """Update progress for a specific video and return overall progress percentage"""
        with self.lock:
            # Update individual video progress
            prev_downloaded = self.bytes_downloaded_map.get(video_id, 0)
            diff = downloaded - prev_downloaded
            if diff > 0:
                self.total_bytes_downloaded += diff
                self.bytes_downloaded_map[video_id] = downloaded
            
            # Update total bytes if not already tracked
            if video_id not in self.total_bytes_map and total > 0:
                self.total_bytes += total
                self.total_bytes_map[video_id] = total
            
            # Calculate overall progress
            return (self.total_bytes_downloaded / self.total_bytes * 100) if self.total_bytes > 0 else 0


class URLValidator:
    """Validates and cleans YouTube URLs"""
    
    YOUTUBE_PATTERN = re.compile(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/")
    WATCH_URL_PATTERN = re.compile(r"(https?://www\.youtube\.com/watch\?v=[\w-]+)")
    
    @classmethod
    def is_valid_youtube_url(cls, url: str) -> bool:
        """Check if URL is a valid YouTube URL"""
        return bool(cls.YOUTUBE_PATTERN.match(url))
    
    @classmethod
    def clean_url(cls, url: str) -> str:
        """Clean and normalize YouTube URL"""
        return url.strip()
    
    @classmethod
    def validate_and_clean_urls(cls, raw_urls: List[str]) -> tuple[List[str], List[str]]:
        """Validate and clean a list of URLs, return valid and invalid URLs"""
        valid_urls = []
        invalid_urls = []
        
        for url in raw_urls:
            url = url.strip()
            if not url:
                continue
                
            if cls.is_valid_youtube_url(url):
                valid_urls.append(cls.clean_url(url))
            else:
                invalid_urls.append(url)
        
        return valid_urls, invalid_urls


class YouTubeDownloaderApp:
    """Main application class for YouTube downloader"""
    
    def __init__(self, root):
        self.root = root
        self._setup_window()
        self._setup_logging()
        
        # State variables
        self.videos: Dict[str, VideoInfo] = {}
        self.selected_items: Set[str] = set()
        self.progress_tracker = ProgressTracker()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.pause_event = threading.Event()
        self.pause_event.set()  # Cho phép chạy mặc định
        
        # UI variables
        self.folder_var = tk.StringVar()
        self.quality_var = tk.StringVar(value="480p")
        self.mode_var = tk.StringVar(value="video")
        
        self._create_widgets()
        self._show_startup_info()
    
    def _setup_window(self):
        """Configure main window"""
        self.root.title("YouTube Downloader - Tải video YouTube")

        # Kích thước cửa sổ
        width = 970
        height = 550

        # Lấy kích thước màn hình
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Tính toán vị trí để căn giữa
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)

        # Đặt kích thước và vị trí cửa sổ
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.resizable(False, False)

        try:
            self.root.iconbitmap("icon.ico")
        except Exception as e:
            print(f"Không thể đặt icon: {e}")

    def _show_startup_info(self):
        def open_url(url):
            webbrowser.open(url)

        popup = tk.Toplevel()
        popup.title("Thông tin ứng dụng")
        popup.geometry("470x200")
        popup.resizable(False, False)

        try:
            popup.iconbitmap("icon.ico")
        except:
            pass

        popup.update_idletasks()
        w = popup.winfo_width()
        h = popup.winfo_height()
        x = (popup.winfo_screenwidth() // 2) - (w // 2)
        y = (popup.winfo_screenheight() // 2) - (h // 2)
        popup.geometry(f"{w}x{h}+{x}+{y}")

        info_lines = [
            "YouTube Downloader",
            "Developer: HaiHai-17",
            "Email: Guen170102@gmail.com",
            "Language: Python",
            "Version: 1.1.0",
        ]

        for line in info_lines:
            tk.Label(popup, text=line, anchor="w").pack(fill="x", padx=10, pady=2)

        # Liên kết GitHub
        link_github = tk.Label(popup, text="GitHub: https://github.com/HaiHai-17/ToolDownloadYoutube", fg="blue", cursor="hand2")
        link_github.pack(padx=10, pady=5)
        link_github.bind("<Button-1>", lambda e: open_url("https://github.com/HaiHai-17/ToolDownloadYoutube"))

        # Liên kết Download
        link_download = tk.Label(popup, text="Download: https://github.com/HaiHai-17/ToolDownloadYoutube/releases", fg="blue", cursor="hand2")
        link_download.pack(padx=10, pady=5)
        link_download.bind("<Button-1>", lambda e: open_url("https://github.com/HaiHai-17/ToolDownloadYoutube/releases"))

    
    def _setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            filename='youtube_downloader.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            encoding='utf-8'
        )
        self.logger = logging.getLogger(__name__)
    
    def _create_widgets(self):
        """Create and layout all UI widgets"""
        self._create_input_section()
        self._create_options_section()
        self._create_video_list()
        self._create_buttons()
        self._create_status_section()
        self._configure_grid()
    
    def _create_input_section(self):
        """Create URL input section"""
        tk.Label(self.root, text="URL YouTube (mỗi dòng 1 link):").grid(
            row=0, column=0, sticky='w', padx=10, pady=5
        )
        self.url_text = tk.Text(self.root, height=5, width=100)
        self.url_text.grid(row=1, column=0, columnspan=7, padx=10, sticky='ew')
    
    def _create_options_section(self):
        """Create options section (mode, folder, quality)"""
        # Mode selection
        tk.Label(self.root, text="Chế độ:").grid(row=2, column=0, sticky='w', padx=10)
        mode_frame = tk.Frame(self.root)
        mode_frame.grid(row=2, column=1, columnspan=2, sticky='w')
        tk.Radiobutton(mode_frame, text="Video", variable=self.mode_var, value="video").pack(side='left')
        def on_playlist_selected():
            self.mode_var.set("playlist")
            messagebox.showinfo(
                "Chú ý",
                "Playlist YouTube phải ở chế độ **công khai**.\nNếu ở chế độ **riêng tư** thì **không tải được**!"
            )

        tk.Radiobutton(
            mode_frame, text="Playlist", variable=self.mode_var, value="playlist",
            command=on_playlist_selected
        ).pack(side='left')
        
        # Folder selection
        tk.Label(self.root, text="Thư mục lưu:").grid(row=3, column=0, sticky='w', padx=10)
        folder_frame = tk.Frame(self.root)
        folder_frame.grid(row=3, column=1, columnspan=5, sticky='ew', pady=5)
        tk.Entry(folder_frame, textvariable=self.folder_var, width=65).pack(side='left', fill='x', expand=True)
        tk.Button(folder_frame, text="Chọn", command=self._choose_folder).pack(side='right', padx=(5, 0))
        
        # Quality selection
        tk.Label(self.root, text="Chất lượng:").grid(row=4, column=0, sticky='w', padx=10)
        quality_combo = ttk.Combobox(
            self.root, 
            textvariable=self.quality_var, 
            values=["480p", "720p", "1080p", "mp3"],
            state="readonly"
        )
        quality_combo.grid(row=4, column=1, sticky='w')

        # Playlist limit selection
        tk.Label(self.root, text="Giới hạn playlist:").grid(row=4, column=2, sticky='w', padx=10)
        self.playlist_limit_var = tk.StringVar(value="100")
        playlist_limit_combo = ttk.Combobox(
            self.root,
            textvariable=self.playlist_limit_var,
            values=["100", "200", "500", "Tất cả"],
            state="readonly",
            width=10
        )
        playlist_limit_combo.grid(row=4, column=3, sticky='w')
    
    def _create_video_list(self):
        """Create video list treeview"""
        columns = ("Chọn", "ID", "Tiêu đề", "Thời lượng", "Trạng thái", "Tiến độ", "Kích thước")
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings", height=12)
        
        # Configure columns
        column_widths = {"Chọn": 60, "ID": 120, "Tiêu đề": 200, "Thời lượng": 80, 
                        "Trạng thái": 100, "Tiến độ": 80, "Kích thước": 100}
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=column_widths.get(col, 100), minwidth=50)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=6, column=0, columnspan=6, padx=10, pady=10, sticky='nsew')
        scrollbar.grid(row=6, column=6, sticky='ns', pady=10)
        
        # Bind events
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_double_click)
    
    def _create_buttons(self):
        """Create button section"""
        btn_frame = tk.Frame(self.root)
        btn_frame.grid(row=7, column=0, columnspan=7, pady=10)
        
        buttons = [
            ("Phân tích", self._analyze_urls),
            ("Tải xuống", self._download_selected),
            ("Tạm dừng / Tiếp tục", self._toggle_pause),
            ("Tải lại lỗi", self._retry_failed_downloads),
            ("Chọn tất cả", self._select_all),
            ("Bỏ chọn tất cả", self._deselect_all),
            ("Lưu danh sách", self._save_urls),
            ("Mở danh sách", self._load_urls),
            ("Xoá đã chọn", self._delete_selected),
            ("Xoá tất cả", self._clear_all)
        ]
        
        for i, (text, command) in enumerate(buttons):
            tk.Button(btn_frame, text=text, command=command).grid(row=0, column=i, padx=5)
    
    def _create_status_section(self):
        """Create status section with progress bar"""
        self.status_label = tk.Label(self.root, text="Sẵn sàng", anchor="w")
        self.status_label.grid(row=8, column=0, columnspan=7, sticky="ew", padx=10)
        
        self.progress = ttk.Progressbar(self.root, mode='determinate')
        self.progress.grid(row=9, column=0, columnspan=7, sticky='ew', padx=10, pady=(0, 10))
        self.progress.grid_remove()  # Hide initially
    
    def _configure_grid(self):
        """Configure grid weights for proper resizing"""
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(6, weight=1)
    
    def _choose_folder(self):
        """Open folder selection dialog"""
        folder = filedialog.askdirectory()
        if folder:
            self.folder_var.set(folder)
    
    def _analyze_urls(self):
        """Start URL analysis in a separate thread"""
        threading.Thread(target=self._analyze_urls_worker, daemon=True).start()
    
    def _analyze_urls_worker(self):
        """Worker function for URL analysis"""
        self._show_progress("Đang phân tích URL...")
        
        try:
            raw_urls = self.url_text.get("1.0", tk.END).strip().splitlines()
            valid_urls, invalid_urls = URLValidator.validate_and_clean_urls(raw_urls)
            
            if invalid_urls:
                self.root.after(0, lambda: messagebox.showwarning(
                    "Link không hợp lệ",
                    f"Có {len(invalid_urls)} link không hợp lệ đã bị bỏ qua:\n" + 
                    "\n".join(invalid_urls[:5]) + ("..." if len(invalid_urls) > 5 else "")
                ))
            
            if not valid_urls:
                self.root.after(0, lambda: messagebox.showwarning(
                    "Không có URL hợp lệ",
                    "Vui lòng nhập ít nhất một URL YouTube hợp lệ."
                ))
                return
            
            # Clear existing videos
            self._clear_video_list()
            
            # Process each URL
            total_urls = len(valid_urls)
            for i, url in enumerate(valid_urls, 1):
                self.root.after(0, lambda i=i, total=total_urls: self._update_status(
                    f"Đang xử lý URL {i}/{total}..."
                ))
                
                self._process_url(url)
            
            # Final status update
            total_videos = len(self.videos)
            self.root.after(0, lambda: self._update_status(
                f"Phân tích hoàn tất: {total_videos} video từ {total_urls} URL"
            ))
            
        except Exception as e:
            self.logger.error(f"Error analyzing URLs: {e}")
            self.root.after(0, lambda: self._update_status(f"Lỗi phân tích: {e}"))
        finally:
            self.root.after(0, self._hide_progress)
    
    def _process_url(self, url: str):
        try:
            self.root.after(0, lambda: self._update_status(f"Đang xử lý: {url[:50]}..."))

            # Gọi hàm xử lý và hiển thị trực tiếp trong _extract_playlist_info
            video_infos = self._get_video_info(url)

            if not video_infos:
                self.root.after(0, lambda: self._update_status(f"Không thể trích xuất thông tin từ: {url}"))
                return

            # Chỉ ghi log, không thêm vào Treeview nữa
            self.logger.info(f"Đã xử lý {len(video_infos)} video từ {url}")

        except Exception as e:
            self.logger.error(f"Error processing URL {url}: {e}")
            self.root.after(0, lambda: self._update_status(f"Lỗi xử lý URL: {str(e)[:50]}..."))

    def _clean_title(self, title: str) -> str:
        """Clean and truncate video title"""
        if not title:
            return "Không rõ"
        
        # Remove problematic characters
        cleaned = re.sub(r'[<>:"/\\|?*]', '', title)
        # Truncate if too long
        return cleaned[:60] + "..." if len(cleaned) > 60 else cleaned
    
    def _get_video_info(self, url: str) -> List[dict]:
        """Extract video information from URL"""
        # Check if this is a playlist URL
        is_playlist = self._is_playlist_url(url)
        
        if is_playlist:
            return self._extract_playlist_info(url)
        else:
            return self._extract_single_video_info(url)
    
    def _is_playlist_url(self, url: str) -> bool:
        """Check if URL is a playlist URL"""
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        
        # Check for playlist indicators
        return (
            'list=' in url or 
            '/playlist?' in url or
            'list' in query_params or
            self.mode_var.get() == "playlist"
        )
    
    def _extract_playlist_info(self, url: str) -> List[dict]:
        ydl_opts = {
            'quiet': False,
            'skip_download': True,
            'extract_flat': True,      # Lấy danh sách video đơn giản
            'no_warnings': True,
            'ignoreerrors': True,
            'noplaylist': False        # Cho phép tải cả playlist
        }

        video_list = []

        try:
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)

            if 'list' in query_params:
                playlist_id = query_params['list'][0]
                playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            else:
                playlist_url = url

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.root.after(0, lambda: self._update_status("Đang quét playlist..."))

                playlist_info = ydl.extract_info(playlist_url, download=False)

                if not playlist_info:
                    return []

                entries = playlist_info.get('entries', [])
                total = len(entries)

                self.root.after(0, lambda: messagebox.showinfo(
                "Playlist phát hiện",
                f"Playlist có {total} video."
            ))

            # Lấy giới hạn từ Combobox
            limit_str = self.playlist_limit_var.get()
            if limit_str == "Tất cả" and total > 500:
                self.root.after(0, lambda: messagebox.showwarning(
                "Cảnh báo hiệu năng",
                f"Playlist có {total} video.\nTải toàn bộ có thể mất nhiều thời gian hoặc làm chậm ứng dụng."
            ))
                
                try:
                    limit = int(limit_str)
                    if total > limit:
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Giới hạn playlist",
                            f"Chỉ tải {limit} video đầu tiên trong số {total} video."
                        ))
                        entries = entries[:limit]
                        total = limit
                except ValueError:
                    self.logger.warning("Không thể đọc giới hạn playlist từ Combobox.")

                for index, entry in enumerate(entries):
                    while not self.pause_event.is_set():
                        time.sleep(0.1)

                    if not entry or not entry.get('url'):
                        continue

                    try:
                        # Lấy đầy đủ thông tin video
                        video_info = ydl.extract_info(entry['url'], download=False)
                        if not video_info or 'id' not in video_info:
                            continue

                        video = VideoInfo(
                            id=video_info['id'],
                            title=self._clean_title(video_info.get('title', "Không rõ")),
                            duration=self._format_duration(video_info.get("duration", 0)),
                            url=f"https://www.youtube.com/watch?v={video_info['id']}"
                        )

                        if video.id not in self.videos:
                            self.videos[video.id] = video
                            self.selected_items.add(video.id)
                            self.root.after(0, self._add_video_to_tree, video)

                        # Cập nhật tiến độ
                        progress = (index + 1) / total * 100
                        msg = f"Đang quét playlist: {index+1}/{total} video ({progress:.1f}%)"
                        self.root.after(0, partial(self._update_status, msg))

                        video_list.append(video_info)

                    except Exception as e:
                        self.logger.error(f"Lỗi khi tải video {entry.get('url', 'unknown')}: {e}")

            return video_list

        except Exception as e:
            self.logger.error(f"Lỗi khi trích xuất playlist {url}: {e}")
            self.root.after(0, lambda: self._update_status(f"Lỗi quét playlist: {str(e)[:50]}..."))
            return []
    
    def _extract_single_video_info(self, url: str) -> List[dict]:
        """Extract info for a single video"""
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'extract_flat': False,
            'no_warnings': True
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return [info] if info and info.get('id') else []
        except Exception as e:
            self.logger.error(f"Error extracting video info {url}: {e}")
            return []
    
    def _add_video_to_tree(self, video: VideoInfo):
        """Add video to treeview"""
        self.tree.insert('', 'end', iid=video.id, values=(
            "✓", video.id, video.title, video.duration, 
            video.status, video.progress, video.size
        ))
    
    def _download_selected(self):
        """Start downloading selected videos"""
        if not self.folder_var.get():
            messagebox.showwarning("Thiếu thư mục", "Vui lòng chọn thư mục lưu video.")
            return
        
        selected_videos = [vid for vid in self.selected_items if vid in self.videos]
        if not selected_videos:
            messagebox.showwarning("Chưa chọn video", "Vui lòng chọn ít nhất một video để tải.")
            return
        
        threading.Thread(target=self._download_worker, args=(selected_videos,), daemon=True).start()
    
    def _download_worker(self, video_ids: List[str]):
        """Worker function for downloading videos"""
        self.progress_tracker.reset()
        self._show_progress("Bắt đầu tải...")
        
        futures = []
        for video_id in video_ids:
            while not self.pause_event.is_set():
                time.sleep(0.1)

            if video_id in self.videos:
                future = self.executor.submit(self._download_single_video, video_id)
                futures.append(future)
        
        # Wait for all downloads to complete
        for future in futures:
            try:
                future.result()
            except Exception as e:
                self.logger.error(f"Download error: {e}")
        
        self.root.after(0, lambda: self._update_status("Tải xuống hoàn tất"))
        self.root.after(0, self._hide_progress)
    
    def _download_single_video(self, video_id: str):
        """Download a single video"""
        video = self.videos[video_id]
        self._update_video_status(video_id, "Đang tải")
        
        try:
            quality = self.quality_var.get()
            folder = self.folder_var.get()
            
            if quality == "mp3":
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(folder, '%(title)s.%(ext)s'),
                    'progress_hooks': [self._create_progress_hook(video_id)],
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
                    'progress_hooks': [self._create_progress_hook(video_id)],
                }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video.url])
            
            self._update_video_status(video_id, "Hoàn tất")
            
        except Exception as e:
            self.logger.error(f"Error downloading {video_id}: {e}")
            self._update_video_status(video_id, "Lỗi")
    
    def _create_progress_hook(self, video_id: str):
        """Create progress hook for a specific video"""
        def hook(d):
            if d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                
                # Update progress tracker
                overall_progress = self.progress_tracker.update_progress(video_id, downloaded, total)
                
                # Extract percentage
                percent_str = self._extract_percentage(d.get('_percent_str', ''))
                
                # Update UI in main thread
                self.root.after(0, lambda: self._update_video_progress(
                    video_id, percent_str, total, overall_progress
                ))
                
            elif d['status'] == 'finished':
                self.root.after(0, lambda: self.tree.set(video_id, "Tiến độ", "100%"))
        
        return hook
    
    def _extract_percentage(self, percent_str: str) -> str:
        """Extract percentage from yt-dlp progress string"""
        match = re.match(r"(\d+)", percent_str.strip())
        return f"{match.group(1)}%" if match else "0%"
    
    def _update_video_progress(self, video_id: str, percent: str, total_bytes: int, overall_progress: float):
        """Update video progress in UI"""
        if self.tree.exists(video_id):
            self.tree.set(video_id, "Tiến độ", percent)
            
            if total_bytes > 0:
                size_mb = round(total_bytes / (1024 * 1024), 2)
                self.tree.set(video_id, "Kích thước", f"{size_mb} MB")
            
            # Update overall progress
            self.progress['value'] = overall_progress
            downloaded_mb = self.progress_tracker.total_bytes_downloaded / (1024 * 1024)
            total_mb = self.progress_tracker.total_bytes / (1024 * 1024)
            self._update_status(f"Tổng tiến độ: {overall_progress:.1f}% - {downloaded_mb:.1f}/{total_mb:.1f} MB")
    
    def _update_video_status(self, video_id: str, status: str):
        """Update video status in UI"""
        self.root.after(0, lambda: self.tree.set(video_id, "Trạng thái", status) if self.tree.exists(video_id) else None)
    
    def _on_tree_click(self, event):
        """Handle tree click events"""
        col = self.tree.identify_column(event.x)
        if col == '#1':  # "Chọn" column
            row_id = self.tree.identify_row(event.y)
            if row_id:
                self._toggle_selection(row_id)
    
    def _on_double_click(self, event):
        """Handle double-click to remove video"""
        item = self.tree.identify_row(event.y)
        if item:
            if messagebox.askyesno("Xoá", f"Xoá video '{self.videos[item].title}'?"):
                self._remove_video(item)

    def _toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self._update_status("⏸ Đã tạm dừng")
        else:
            self.pause_event.set()
            self._update_status("▶️ Tiếp tục")

    def _retry_failed_downloads(self):
        failed_ids = [vid_id for vid_id, video in self.videos.items() if video.status == "Lỗi"]
        if not failed_ids:
            messagebox.showinfo("Thông báo", "Không có video lỗi để tải lại.")
            return
        self._update_status(f"Đang tải lại {len(failed_ids)} video bị lỗi...")
        threading.Thread(target=self._download_worker, args=(failed_ids,), daemon=True).start()
    
    def _toggle_selection(self, video_id: str):
        """Toggle video selection"""
        if video_id in self.selected_items:
            self.selected_items.remove(video_id)
            self.tree.set(video_id, "Chọn", "")
        else:
            self.selected_items.add(video_id)
            self.tree.set(video_id, "Chọn", "✓")
    
    def _select_all(self):
        """Select all videos"""
        for video_id in self.videos:
            self.selected_items.add(video_id)
            self.tree.set(video_id, "Chọn", "✓")
    
    def _deselect_all(self):
        """Deselect all videos"""
        self.selected_items.clear()
        for video_id in self.videos:
            self.tree.set(video_id, "Chọn", "")
    
    def _delete_selected(self):
        """Delete selected videos from list"""
        if not self.selected_items:
            messagebox.showinfo("Thông báo", "Chưa chọn video nào để xóa.")
            return
        
        if messagebox.askyesno("Xác nhận", f"Xóa {len(self.selected_items)} video đã chọn?"):
            for video_id in list(self.selected_items):
                self._remove_video(video_id)
    
    def _remove_video(self, video_id: str):
        """Remove a video from the list"""
        if video_id in self.videos:
            del self.videos[video_id]
        self.selected_items.discard(video_id)
        if self.tree.exists(video_id):
            self.tree.delete(video_id)
    
    def _clear_video_list(self):
        """Clear the video list"""
        self.videos.clear()
        self.selected_items.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
    
    def _clear_all(self):
        """Clear all data"""
        if messagebox.askyesno("Xác nhận", "Xoá toàn bộ danh sách URL và video?"):
            self._clear_video_list()
            self.url_text.delete("1.0", tk.END)
            self._update_status("Đã xoá toàn bộ danh sách")
    
    def _save_urls(self):
        """Save URLs to file"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt", 
            filetypes=[("Text Files", "*.txt")]
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.url_text.get("1.0", tk.END))
                messagebox.showinfo("Thành công", "Danh sách URL đã được lưu.")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể lưu file: {e}")
    
    def _load_urls(self):
        """Load URLs from file"""
        file_path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.url_text.delete("1.0", tk.END)
                    self.url_text.insert(tk.END, f.read())
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể đọc file: {e}")
    
    def _show_progress(self, message: str):
        """Show progress bar with message"""
        self.progress.grid()
        self.progress.start(10)
        self._update_status(message)
    
    def _hide_progress(self):
        """Hide progress bar"""
        self.progress.stop()
        self.progress.grid_remove()
    
    def _update_status(self, message: str):
        """Update status label"""
        self.status_label.config(text=message)
    
    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Format duration in HH:MM:SS format"""
        if not seconds:
            return "--:--:--"
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)


def main():
    """Main entry point"""
    root = tk.Tk()
    app = YouTubeDownloaderApp(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(app, 'executor'):
            app.executor.shutdown(wait=True)


if __name__ == "__main__":
    main()