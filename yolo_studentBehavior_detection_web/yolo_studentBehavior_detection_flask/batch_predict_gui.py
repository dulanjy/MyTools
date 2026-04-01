import os
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import json

# Optional: import cv2 only if needed for preview windows
# import cv2

try:
    from ultralytics import YOLO
except Exception as e:
    YOLO = None


SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _resolve_model_path(path_str: str) -> str:
    p = Path(path_str)
    if p.exists():
        return str(p)
    script_dir = Path(__file__).resolve().parent
    alt = script_dir / p
    if alt.exists():
        return str(alt)
    return path_str


def _gather_images_from_folder(folder: str) -> list[str]:
    imgs = []
    if not folder:
        return imgs
    for ext in SUPPORTED_EXTS:
        imgs.extend(str(p) for p in Path(folder).rglob(f"*{ext}"))
    return imgs


class YoloBatchGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("YOLO 批量图片预测")
        self.root.geometry("820x620")
        self.root.minsize(820, 600)

        # State
        self.model_path_var = tk.StringVar()
        self.images_info_var = tk.StringVar(value="未选择图片")
        self.output_parent_var = tk.StringVar(value=str(Path(__file__).resolve().parent / "runs" / "detect"))
        self.run_name_var = tk.StringVar(value=f"predict_gui_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        self.json_dir_var = tk.StringVar(value="")
        self.device_var = tk.StringVar(value="0")  # e.g. "0" or "cpu"
        self.conf_var = tk.DoubleVar(value=0.25)
        self.imgsz_var = tk.IntVar(value=640)
        self.save_crop_var = tk.BooleanVar(value=False)
        self.exist_ok_var = tk.BooleanVar(value=True)

        self.selected_images = []
        self.run_save_dir = None
        self.running = False

        # Config file to remember last selections
        self.config_path = Path(__file__).resolve().parent / ".yolo_batch_gui_config.json"
        self._load_config()

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 6}

        # Model row
        fr_model = ttk.Frame(self.root)
        fr_model.pack(fill="x", **pad)
        ttk.Label(fr_model, text="模型 (.pt)").pack(side="left")
        ttk.Entry(fr_model, textvariable=self.model_path_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(fr_model, text="浏览…", command=self._browse_model).pack(side="left")

        # Images row
        fr_imgs = ttk.LabelFrame(self.root, text="图片选择")
        fr_imgs.pack(fill="x", **pad)
        ttk.Button(fr_imgs, text="选择图片(可多选)…", command=self._browse_images).pack(side="left", padx=4)
        ttk.Button(fr_imgs, text="选择文件夹…", command=self._browse_folder).pack(side="left", padx=4)
        ttk.Button(fr_imgs, text="清空", command=self._clear_images).pack(side="left", padx=4)
        ttk.Label(fr_imgs, textvariable=self.images_info_var).pack(side="left", padx=10)

        # Params row
        fr_params = ttk.LabelFrame(self.root, text="参数")
        fr_params.pack(fill="x", **pad)
        # conf
        ttk.Label(fr_params, text="conf").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(fr_params, width=8, textvariable=self.conf_var).grid(row=0, column=1, sticky="w")
        # imgsz
        ttk.Label(fr_params, text="imgsz").grid(row=0, column=2, sticky="w", padx=12)
        ttk.Entry(fr_params, width=8, textvariable=self.imgsz_var).grid(row=0, column=3, sticky="w")
        # device
        ttk.Label(fr_params, text="device").grid(row=0, column=4, sticky="w", padx=12)
        ttk.Entry(fr_params, width=10, textvariable=self.device_var).grid(row=0, column=5, sticky="w")
        # checkboxes
        ttk.Checkbutton(fr_params, text="save-crop", variable=self.save_crop_var).grid(row=0, column=6, sticky="w", padx=16)
        ttk.Checkbutton(fr_params, text="exist-ok", variable=self.exist_ok_var).grid(row=0, column=7, sticky="w")

        for i in range(8):
            fr_params.grid_columnconfigure(i, weight=0)

        # Output row
        fr_out = ttk.LabelFrame(self.root, text="输出")
        fr_out.pack(fill="x", **pad)
        ttk.Label(fr_out, text="Project 目录").pack(side="left")
        ttk.Entry(fr_out, textvariable=self.output_parent_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(fr_out, text="浏览…", command=self._browse_output_parent).pack(side="left")
        ttk.Label(fr_out, text="Run 名称").pack(side="left", padx=8)
        ttk.Entry(fr_out, width=24, textvariable=self.run_name_var).pack(side="left")
        # JSON dir line
        fr_json = ttk.Frame(self.root)
        fr_json.pack(fill="x", **pad)
        ttk.Label(fr_json, text="JSON 单独保存到").pack(side="left")
        ttk.Entry(fr_json, textvariable=self.json_dir_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(fr_json, text="浏览…", command=self._browse_json_dir).pack(side="left")

        # Actions row
        fr_act = ttk.Frame(self.root)
        fr_act.pack(fill="x", **pad)
        self.btn_run = ttk.Button(fr_act, text="开始预测", command=self.on_run)
        self.btn_run.pack(side="left")
        ttk.Button(fr_act, text="打开输出目录", command=self._open_output_dir).pack(side="left", padx=8)

        # Progress
        fr_prog = ttk.Frame(self.root)
        fr_prog.pack(fill="x", **pad)
        ttk.Label(fr_prog, text="进度").pack(side="left")
        self.prog = ttk.Progressbar(fr_prog, length=300, mode="determinate")
        self.prog.pack(side="left", padx=8)
        self.prog_val = ttk.Label(fr_prog, text="0/0")
        self.prog_val.pack(side="left")

        # Log
        fr_log = ttk.LabelFrame(self.root, text="日志")
        fr_log.pack(fill="both", expand=True, **pad)
        self.txt = tk.Text(fr_log, height=16)
        self.txt.pack(fill="both", expand=True)

    # UI helpers
    def _browse_model(self) -> None:
        init_dir = None
        if self.model_path_var.get():
            init_dir = str(Path(self.model_path_var.get()).parent)
        elif getattr(self, "last_model_dir", None):
            init_dir = self.last_model_dir
        path = filedialog.askopenfilename(
            title="选择模型权重 (.pt)",
            filetypes=[("PyTorch Weights", "*.pt"), ("All Files", "*.*")],
            initialdir=init_dir if init_dir else None,
        )
        if path:
            self.model_path_var.set(path)
            self.last_model_dir = str(Path(path).parent)
            self._save_config()

    def _browse_images(self) -> None:
        init_dir = getattr(self, "last_images_dir", None)
        files = filedialog.askopenfilenames(
            title="选择图片(可多选)",
            filetypes=[("Images", ".jpg .jpeg .png .bmp .webp"), ("All Files", "*.*")],
            initialdir=init_dir if init_dir else None,
        )
        if files:
            # Keep only supported
            filtered = [f for f in files if Path(f).suffix.lower() in SUPPORTED_EXTS]
            self.selected_images = list(dict.fromkeys(self.selected_images + filtered))  # de-dup, keep order
            self.images_info_var.set(f"已选择 {len(self.selected_images)} 张图片")
            # Remember the folder of first image
            try:
                self.last_images_dir = str(Path(filtered[0]).parent)
            except Exception:
                pass
            self._save_config()

    def _browse_folder(self) -> None:
        init_dir = getattr(self, "last_images_dir", None)
        folder = filedialog.askdirectory(title="选择图片文件夹", initialdir=init_dir if init_dir else None)
        if folder:
            imgs = _gather_images_from_folder(folder)
            if imgs:
                self.selected_images = list(dict.fromkeys(self.selected_images + imgs))
                self.images_info_var.set(f"已选择 {len(self.selected_images)} 张图片")
            else:
                messagebox.showinfo("提示", "该文件夹内未找到支持的图片类型。")
            self.last_images_dir = folder
            self._save_config()

    def _clear_images(self) -> None:
        self.selected_images = []
        self.images_info_var.set("未选择图片")

    def _browse_output_parent(self) -> None:
        init_dir = None
        if self.output_parent_var.get():
            init_dir = self.output_parent_var.get()
        elif getattr(self, "last_project_dir", None):
            init_dir = self.last_project_dir
        folder = filedialog.askdirectory(title="选择 Project 目录 (保存父目录)", initialdir=init_dir if init_dir else None)
        if folder:
            self.output_parent_var.set(folder)
            self.last_project_dir = folder
            self._save_config()

    def _open_output_dir(self) -> None:
        if self.run_save_dir and self.run_save_dir.exists():
            try:
                os.startfile(self.run_save_dir)  # Windows
            except Exception:
                messagebox.showinfo("提示", f"输出路径：{self.run_save_dir}")
        else:
            base = Path(self.output_parent_var.get()) / self.run_name_var.get()
            if base.exists():
                try:
                    os.startfile(base)
                except Exception:
                    messagebox.showinfo("提示", f"输出路径：{base}")
            else:
                messagebox.showinfo("提示", "当前还没有可打开的输出目录。")

    def _browse_json_dir(self) -> None:
        init_dir = None
        if self.json_dir_var.get():
            init_dir = self.json_dir_var.get()
        elif getattr(self, "last_json_dir", None):
            init_dir = self.last_json_dir
        folder = filedialog.askdirectory(title="选择 JSON 输出目录 (可选)", initialdir=init_dir if init_dir else None)
        if folder:
            self.json_dir_var.set(folder)
            self.last_json_dir = folder
            self._save_config()

    def log(self, msg: str) -> None:
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")

    def on_run(self) -> None:
        if self.running:
            return
        if YOLO is None:
            messagebox.showerror("错误", "未安装 ultralytics 库，请先安装: pip install ultralytics")
            return
        model_path = self.model_path_var.get().strip()
        if not model_path:
            messagebox.showerror("错误", "请先选择模型文件(.pt)")
            return
        if not self.selected_images:
            messagebox.showerror("错误", "请先选择图片 (可多选或选择文件夹)")
            return

        # Freeze UI state and start worker
        self.running = True
        self.btn_run.config(state="disabled")
        self.prog.config(maximum=len(self.selected_images), value=0)
        self.prog_val.config(text=f"0/{len(self.selected_images)}")
        self.txt.delete("1.0", "end")

        t = threading.Thread(target=self._run_worker, daemon=True)
        t.start()

    def _run_worker(self) -> None:
        try:
            model_path = _resolve_model_path(self.model_path_var.get().strip())
            conf = float(self.conf_var.get())
            imgsz = int(self.imgsz_var.get())
            device = self.device_var.get().strip()
            save_crop = bool(self.save_crop_var.get())
            exist_ok = bool(self.exist_ok_var.get())
            project = Path(self.output_parent_var.get().strip())
            name = self.run_name_var.get().strip()
            json_dir = self.json_dir_var.get().strip()
            if not json_dir:
                json_dir = None

            self._ui(lambda: self.log(f"加载模型: {model_path}"))
            model = YOLO(model_path)
            names = model.names if hasattr(model, "names") else {}

            # We'll use stream=True to update progress per image
            source_list = list(self.selected_images)
            total = len(source_list)
            done = 0
            agg_counts = defaultdict(int)
            first_save_dir = None

            self._ui(lambda: self.log(f"开始推理，共 {total} 张图片"))

            for r in model.predict(
                source=source_list,
                conf=conf,
                imgsz=imgsz,
                device=device,
                save=True,
                save_crop=save_crop,
                project=str(project),
                name=name,
                exist_ok=exist_ok,
                stream=True,
                verbose=False,
            ):
                # Determine save_dir (once)
                if first_save_dir is None:
                    sd = getattr(r, "save_dir", None)
                    if sd is None:
                        sd = project / name
                    first_save_dir = Path(sd)

                # Per-image counts and boxes
                per_counts = defaultdict(int)
                per_boxes = defaultdict(list)
                per_objects = []
                iw = ih = None
                if getattr(r, "orig_shape", None) is not None:
                    try:
                        ih, iw = int(r.orig_shape[0]), int(r.orig_shape[1])
                    except Exception:
                        pass
                if getattr(r, "boxes", None) is not None:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        cname = names.get(cls_id, str(cls_id))
                        per_counts[cname] += 1
                        agg_counts[cname] += 1
                        try:
                            xyxy = [float(v) for v in box.xyxy[0].tolist()]
                        except Exception:
                            xyxy = None
                        try:
                            conf = float(box.conf[0])
                        except Exception:
                            conf = None
                        entry = {"bbox_xyxy": xyxy, "confidence": conf}
                        per_boxes[cname].append(entry)
                        per_objects.append({"label": cname, **entry})

                # Save per-image counts JSON next to saved image(s)
                try:
                    img_stem = Path(getattr(r, "path", "image")).stem
                    payload = {
                        "image": getattr(r, "path", None),
                        "size": {"width": iw, "height": ih} if (iw is not None and ih is not None) else None,
                        "counts": dict(per_counts),
                        "boxes": per_boxes,
                        "objects": per_objects,
                    }
                    if json_dir:
                        out_path = Path(json_dir) / f"{img_stem}_counts.json"
                        Path(json_dir).mkdir(parents=True, exist_ok=True)
                    else:
                        save_dir = Path(getattr(r, "save_dir", first_save_dir or (project / name)))
                        out_path = save_dir / f"{img_stem}_counts.json"
                    out_path.write_text(_json_dumps(payload), encoding="utf-8")
                except Exception as e:
                    self._ui(lambda e=e: self.log(f"[WARN] 写入计数 JSON 失败: {e}"))

                done += 1
                self._ui(lambda d=done, t=total: self._update_progress(d, t))

            # Save aggregated counts
            if first_save_dir is None:
                first_save_dir = project / name
            try:
                if json_dir:
                    Path(json_dir).mkdir(parents=True, exist_ok=True)
                    summary_path = Path(json_dir) / "counts_summary.json"
                else:
                    summary_path = first_save_dir / "counts_summary.json"
                summary_path.write_text(_json_dumps(agg_counts), encoding="utf-8")
            except Exception as e:
                self._ui(lambda e=e: self.log(f"[WARN] 写入汇总 JSON 失败: {e}"))

            self.run_save_dir = first_save_dir
            self._ui(lambda: self.log(f"完成！输出目录: {first_save_dir}"))
            self._ui(lambda: messagebox.showinfo("完成", f"预测完成，输出目录:\n{first_save_dir}"))

        except Exception as e:
            self._ui(lambda e=e: messagebox.showerror("错误", str(e)))
            self._ui(lambda e=e: self.log(f"[ERROR] {e}"))
        finally:
            self._ui(lambda: self._reset_ui())

    def _update_progress(self, done: int, total: int) -> None:
        self.prog.config(value=done, maximum=total)
        self.prog_val.config(text=f"{done}/{total}")

    def _reset_ui(self) -> None:
        self.running = False
        self.btn_run.config(state="normal")

    def _ui(self, fn) -> None:
        # Schedule UI updates safely from worker thread
        self.root.after(0, fn)

    # Config persistence
    def _load_config(self) -> None:
        try:
            if self.config_path.exists():
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
            else:
                data = {}
        except Exception:
            data = {}

        # Populate remembered paths
        self.last_model_dir = data.get("last_model_dir")
        self.last_images_dir = data.get("last_images_dir")
        self.last_project_dir = data.get("last_project_dir")
        self.last_json_dir = data.get("last_json_dir")

        # Prefill fields if present
        if data.get("model_path"):
            self.model_path_var.set(data.get("model_path"))
        if data.get("project_dir"):
            self.output_parent_var.set(data.get("project_dir"))
        if data.get("json_dir"):
            self.json_dir_var.set(data.get("json_dir"))

    def _save_config(self) -> None:
        try:
            data = {
                "last_model_dir": getattr(self, "last_model_dir", None),
                "last_images_dir": getattr(self, "last_images_dir", None),
                "last_project_dir": getattr(self, "last_project_dir", None),
                "last_json_dir": getattr(self, "last_json_dir", None),
                "model_path": self.model_path_var.get() or None,
                "project_dir": self.output_parent_var.get() or None,
                "json_dir": self.json_dir_var.get() or None,
            }
            self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def _json_dumps(d: dict) -> str:
    # avoid importing json at top-level to keep startup fast
    import json

    # defaultdict -> normal dict
    if isinstance(d, defaultdict):
        d = dict(d)
    return json.dumps(d, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    root = tk.Tk()
    app = YoloBatchGUI(root)
    root.mainloop()
