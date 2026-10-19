from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

import pymupdf as fitz
import pytesseract
from PIL import Image, ImageGrab, ImageTk
from pytesseract import TesseractNotFoundError


class OCRApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("متن‌خوان تصویر و PDF")
        self.root.geometry("950x700")
        self.root.minsize(700, 500)

        self.language = tk.StringVar(value="fas+eng")
        self.source = tk.StringVar(value="هنوز فایلی انتخاب نشده است")
        self.status = tk.StringVar(value="آماده")
        self._busy = False

        self._build_ui()

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.configure("TButton", padding=7)
        style.configure("TLabel", font=("Segoe UI", 10))

        controls = ttk.Frame(self.root, padding=(12, 12, 12, 8))
        controls.pack(fill="x")

        self.open_button = ttk.Button(
            controls, text="انتخاب عکس یا PDF", command=self.open_file
        )
        self.open_button.pack(side="right", padx=(0, 6))
        self.capture_button = ttk.Button(
            controls, text="انتخاب ناحیه از صفحه", command=self.select_screen_region
        )
        self.capture_button.pack(side="right", padx=6)
        self.tesseract_button = ttk.Button(
            controls, text="تنظیم مسیر Tesseract", command=self.set_tesseract_path
        )
        self.tesseract_button.pack(side="right", padx=6)

        language_frame = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        language_frame.pack(fill="x")
        ttk.Label(language_frame, text="زبان OCR (مثلاً fas+eng):").pack(
            side="right", padx=(0, 8)
        )
        ttk.Entry(
            language_frame, textvariable=self.language, width=16, justify="right"
        ).pack(side="right")

        ttk.Label(
            self.root,
            textvariable=self.source,
            anchor="e",
            padding=(12, 4),
        ).pack(fill="x")

        output_frame = ttk.Frame(self.root, padding=(12, 4, 12, 8))
        output_frame.pack(fill="both", expand=True)
        self.output = tk.Text(
            output_frame,
            wrap="word",
            undo=True,
            font=("Segoe UI", 11),
            padx=10,
            pady=10,
            relief="solid",
            borderwidth=1,
        )
        scrollbar = ttk.Scrollbar(
            output_frame, orient="vertical", command=self.output.yview
        )
        self.output.configure(yscrollcommand=scrollbar.set)
        self.output.pack(side="right", fill="both", expand=True)
        scrollbar.pack(side="left", fill="y")

        footer = ttk.Frame(self.root, padding=(12, 4, 12, 12))
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status, anchor="e").pack(
            side="right", fill="x", expand=True
        )
        ttk.Button(footer, text="پاک کردن متن", command=self.clear_output).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(footer, text="کپی متن", command=self.copy_output).pack(
            side="left", padx=6
        )
        ttk.Button(footer, text="ذخیره متن", command=self.save_output).pack(
            side="left", padx=6
        )

    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="انتخاب عکس یا فایل PDF",
            filetypes=[
                ("عکس و PDF", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.pdf"),
                ("همه فایل‌ها", "*.*"),
            ],
        )
        if not path:
            return

        self.source.set(path)
        language = self.language.get().strip()
        self._run_ocr(
            lambda: self._ocr_file(Path(path), language),
            "در حال استخراج متن از فایل...",
        )

    def set_tesseract_path(self) -> None:
        path = filedialog.askopenfilename(
            title="انتخاب فایل اجرایی Tesseract",
            filetypes=[("Tesseract", "tesseract.exe"), ("همه فایل‌ها", "*.*")],
        )
        if path:
            pytesseract.pytesseract.tesseract_cmd = path
            self.status.set(f"مسیر Tesseract تنظیم شد: {path}")

    def select_screen_region(self) -> None:
        if self._busy:
            return
        try:
            screenshot = ImageGrab.grab()
        except OSError as exc:
            messagebox.showerror("خطا در عکس‌برداری", str(exc), parent=self.root)
            return

        selection = tk.Toplevel(self.root)
        selection.overrideredirect(True)
        selection.attributes("-topmost", True)
        selection.geometry(f"{screenshot.width}x{screenshot.height}+0+0")

        canvas = tk.Canvas(
            selection,
            width=screenshot.width,
            height=screenshot.height,
            cursor="cross",
            highlightthickness=0,
        )
        canvas.pack(fill="both", expand=True)
        background = ImageTk.PhotoImage(screenshot)
        canvas.create_image(0, 0, image=background, anchor="nw")
        canvas.create_rectangle(
            0,
            0,
            screenshot.width,
            42,
            fill="#202020",
            stipple="gray50",
            outline="",
        )
        canvas.create_text(
            screenshot.width // 2,
            21,
            text="برای انتخاب ناحیه، ماوس را بکشید؛ برای لغو Escape را بزنید",
            fill="white",
            font=("Segoe UI", 12),
        )

        start: dict[str, int] = {}
        rectangle: int | None = None

        def begin(event: tk.Event) -> None:
            nonlocal rectangle
            start["x"] = event.x
            start["y"] = event.y
            rectangle = canvas.create_rectangle(
                event.x,
                event.y,
                event.x,
                event.y,
                outline="#00e5ff",
                width=3,
            )

        def drag(event: tk.Event) -> None:
            if rectangle is not None:
                canvas.coords(
                    rectangle, start["x"], start["y"], event.x, event.y
                )

        def finish(event: tk.Event) -> None:
            x1, x2 = sorted((start["x"], event.x))
            y1, y2 = sorted((start["y"], event.y))
            selection.destroy()
            if x2 - x1 < 3 or y2 - y1 < 3:
                self.status.set("ناحیه انتخاب‌شده خیلی کوچک بود.")
                return
            self.source.set("ناحیه انتخاب‌شده از صفحه")
            image = screenshot.crop((x1, y1, x2, y2))
            language = self.language.get().strip()
            self._run_ocr(
                lambda: pytesseract.image_to_string(image, lang=language),
                "در حال خواندن متن ناحیه انتخاب‌شده...",
            )

        canvas.bind("<ButtonPress-1>", begin)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", finish)
        selection.bind("<Escape>", lambda _event: selection.destroy())
        selection.focus_force()
        selection._background_image = background

    def _ocr_file(self, path: Path, language: str) -> str:
        if path.suffix.lower() == ".pdf":
            pages: list[str] = []
            with fitz.open(path) as document:
                total = len(document)
                for index, page in enumerate(document, start=1):
                    self.root.after(
                        0,
                        self.status.set,
                        f"در حال پردازش صفحه {index} از {total}...",
                    )
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    image = Image.frombytes(
                        "RGB", (pixmap.width, pixmap.height), pixmap.samples
                    )
                    text = pytesseract.image_to_string(image, lang=language).strip()
                    pages.append(f"--- صفحه {index} ---\n{text}")
            return "\n\n".join(pages)

        with Image.open(path) as image:
            return pytesseract.image_to_string(image, lang=language)

    def _run_ocr(self, operation: Callable[[], str], busy_message: str) -> None:
        if not self.language.get().strip():
            messagebox.showerror("زبان مشخص نشده", "زبان OCR را وارد کنید.")
            return
        self._set_busy(True)
        self.status.set(busy_message)

        def worker() -> None:
            try:
                result = operation()
            except TesseractNotFoundError:
                self.root.after(0, self._show_tesseract_error)
            except Exception as exc:
                self.root.after(0, self._finish_with_error, str(exc))
            else:
                self.root.after(0, self._finish_with_result, result)

        threading.Thread(target=worker, daemon=True).start()

    def _show_tesseract_error(self) -> None:
        self._set_busy(False)
        self.status.set("Tesseract پیدا نشد.")
        messagebox.showerror(
            "Tesseract پیدا نشد",
            "Tesseract OCR نصب نیست یا در PATH قرار ندارد. آن را نصب کنید یا "
            "از دکمه «تنظیم مسیر Tesseract» مسیر tesseract.exe را انتخاب کنید.",
            parent=self.root,
        )

    def _finish_with_error(self, error: str) -> None:
        self._set_busy(False)
        self.status.set("پردازش با خطا روبه‌رو شد.")
        messagebox.showerror("خطا در OCR", error, parent=self.root)

    def _finish_with_result(self, result: str) -> None:
        self.output.delete("1.0", "end")
        self.output.insert("1.0", result)
        self._set_busy(False)
        self.status.set("استخراج متن تمام شد.")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.open_button.configure(state=state)
        self.capture_button.configure(state=state)
        self.tesseract_button.configure(state=state)

    def clear_output(self) -> None:
        self.output.delete("1.0", "end")

    def copy_output(self) -> None:
        text = self.output.get("1.0", "end-1c")
        if not text:
            self.status.set("متنی برای کپی وجود ندارد.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.set("متن در کلیپ‌بورد کپی شد.")

    def save_output(self) -> None:
        text = self.output.get("1.0", "end-1c")
        if not text:
            self.status.set("متنی برای ذخیره وجود ندارد.")
            return
        path = filedialog.asksaveasfilename(
            title="ذخیره متن استخراج‌شده",
            defaultextension=".txt",
            filetypes=[("فایل متنی", "*.txt"), ("همه فایل‌ها", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("خطا در ذخیره فایل", str(exc), parent=self.root)
            return
        self.status.set(f"متن ذخیره شد: {path}")


def main() -> None:
    root = tk.Tk()
    OCRApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
