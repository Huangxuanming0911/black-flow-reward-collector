from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import os
import queue
import tkinter as tk
from tkinter import messagebox, ttk

from .models import (
    BONUS_SOURCES,
    COMBAT_CONTEXTS,
    LOCATION_CONTEXTS,
    PendingBattle,
    RewardRecord,
)
from .runtime import LiveCollector
from .store import RewardStore


def _mapping(items: tuple[tuple[str, str], ...]) -> tuple[dict[str, str], dict[str, str]]:
    id_to_name = dict(items)
    name_to_id = {name: item_id for item_id, name in items}
    return id_to_name, name_to_id


LOCATION_NAMES, LOCATION_IDS = _mapping(LOCATION_CONTEXTS)
COMBAT_NAMES, COMBAT_IDS = _mapping(COMBAT_CONTEXTS)
BONUS_NAMES, BONUS_IDS = _mapping(BONUS_SOURCES)

PHASE_LABELS = {
    "idle": "○ 尚未开始",
    "connecting": "◌ 正在连接游戏窗口并加载 OCR",
    "monitoring": "● 正在监控，等待战斗结算",
    "settlement": "● 已捕获结算，正在等待奖励",
    "rewards": "● 正在记录本场奖励",
    "finalizing": "● 已返回地图，正在生成统计",
    "review": "● 等待确认本场统计",
    "stopping": "◌ 正在停止",
    "stopped": "○ 采集已停止",
    "error": "● 采集发生错误",
}

PHASE_STYLES = {
    "idle": "Phase.Idle.TLabel",
    "connecting": "Phase.Active.TLabel",
    "monitoring": "Phase.Ready.TLabel",
    "settlement": "Phase.Capture.TLabel",
    "rewards": "Phase.Capture.TLabel",
    "finalizing": "Phase.Active.TLabel",
    "review": "Phase.Review.TLabel",
    "stopping": "Phase.Active.TLabel",
    "stopped": "Phase.Idle.TLabel",
    "error": "Phase.Error.TLabel",
}


class CollectorApp:
    def __init__(self, root: tk.Tk, project_root: Path) -> None:
        self.root = root
        self.project_root = project_root
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.store = RewardStore(project_root / "data" / "records")
        self.live = LiveCollector(
            self.store.root,
            self.events,
        )
        self._toast: tk.Toplevel | None = None
        self._build()
        self.root.after(150, self._poll_events)

    def _build(self) -> None:
        self.root.title("黑流树海 · 战后奖励采集器")
        self.root.geometry("580x420")
        self.root.minsize(540, 390)

        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)
        ttk.Label(
            container,
            text="下一场作战上下文",
            font=("Microsoft YaHei UI", 15, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            container,
            text="可在战后弹窗中再次修改；程序不会点击游戏。",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 14))

        self.floor_var = tk.StringVar(value="1")
        self.location_var = tk.StringVar(
            value=LOCATION_NAMES["main_map"]
        )
        self.combat_var = tk.StringVar(value=COMBAT_NAMES["combat"])
        self.topmost_var = tk.BooleanVar(value=True)
        self.phase_var = tk.StringVar(value=PHASE_LABELS["idle"])
        self.status_var = tk.StringVar(
            value="点击“开始实时采集”后即可切回游戏。"
        )
        self.count_var = tk.StringVar(
            value=f"已保存样本：{len(self.store.read_all())}"
        )

        self._combo_row(
            container,
            2,
            "来源层数",
            self.floor_var,
            ("1", "2", "3", "4", "5", "6", "未知"),
        )
        self._combo_row(
            container,
            3,
            "所在环境",
            self.location_var,
            tuple(LOCATION_NAMES.values()),
        )
        self._combo_row(
            container,
            4,
            "战斗类型",
            self.combat_var,
            tuple(COMBAT_NAMES.values()),
        )

        ttk.Checkbutton(
            container,
            text="确认弹窗置顶",
            variable=self.topmost_var,
        ).grid(row=5, column=1, sticky="w", pady=(10, 4))

        buttons = ttk.Frame(container)
        buttons.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(16, 10),
        )
        self.start_button = ttk.Button(
            buttons,
            text="开始实时采集",
            command=self.start,
        )
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(
            buttons,
            text="停止",
            command=self.stop,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(
            buttons,
            text="手动补录一场",
            command=lambda: self._review(
                PendingBattle(
                    sample_id=datetime.now(UTC).strftime(
                        "%Y%m%dT%H%M%S-manual"
                    ),
                    started_at=datetime.now(UTC).isoformat(),
                )
            ),
        ).pack(side="left")

        status = ttk.LabelFrame(container, text="运行状态", padding=12)
        status.grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(8, 0),
        )
        style = ttk.Style(self.root)
        style.configure(
            "Phase.Idle.TLabel",
            foreground="#666666",
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.configure(
            "Phase.Ready.TLabel",
            foreground="#138a4b",
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.configure(
            "Phase.Capture.TLabel",
            foreground="#b45f06",
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.configure(
            "Phase.Active.TLabel",
            foreground="#1769aa",
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.configure(
            "Phase.Review.TLabel",
            foreground="#6f42c1",
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.configure(
            "Phase.Error.TLabel",
            foreground="#b00020",
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        self.phase_label = ttk.Label(
            status,
            textvariable=self.phase_var,
            style=PHASE_STYLES["idle"],
        )
        self.phase_label.pack(anchor="w")
        ttk.Label(
            status,
            textvariable=self.status_var,
            wraplength=500,
        ).pack(anchor="w", pady=(7, 0))
        ttk.Label(status, textvariable=self.count_var).pack(
            anchor="w",
            pady=(6, 0),
        )
        ttk.Label(
            status,
            text=(
                "提示：奖励出现后正常领取；明确返回地图约 1 秒后弹窗，"
                "无法确认回图时使用 5 秒兜底。"
            ),
            foreground="#555555",
            wraplength=500,
        ).pack(anchor="w", pady=(10, 0))

        container.columnconfigure(1, weight=1)
        container.rowconfigure(7, weight=1)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    @staticmethod
    def _combo_row(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row,
            column=0,
            sticky="w",
            pady=5,
        )
        ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
        ).grid(row=row, column=1, sticky="ew", padx=(18, 0), pady=5)

    def start(self) -> None:
        if self.live.running:
            return
        self.status_var.set("正在连接明日方舟窗口并加载 OCR……")
        self._set_phase("connecting")
        self.live.start()

    def stop(self) -> None:
        if not self.live.running:
            return
        self._set_phase("stopping")
        self.live.stop()

    def _poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "status":
                    self.status_var.set(str(payload))
                elif event == "phase":
                    self._set_phase(str(payload))
                elif event == "error":
                    self.status_var.set(f"错误：{payload}")
                    self._set_phase("error")
                    messagebox.showerror("采集错误", str(payload))
                elif event == "review":
                    self._review(payload)  # type: ignore[arg-type]
        except queue.Empty:
            pass
        self.root.after(150, self._poll_events)

    def _set_phase(self, phase: str) -> None:
        self.phase_var.set(PHASE_LABELS.get(phase, phase))
        self.phase_label.configure(
            style=PHASE_STYLES.get(phase, "Phase.Idle.TLabel")
        )
        running = phase not in ("idle", "stopped", "error")
        self.start_button.configure(
            state="disabled" if running else "normal"
        )
        self.stop_button.configure(
            state="normal" if running else "disabled"
        )
        messages = {
            "monitoring": "采集已启动：正在后台等待结算",
            "settlement": "已捕获结算：正在等待经验与奖励页面",
            "rewards": "正在记录：请正常领取全部奖励",
            "finalizing": "已确认返回地图：即将打开统计",
        }
        if phase in messages:
            self._show_toast(messages[phase])

    def _show_toast(self, message: str) -> None:
        if self._toast is not None:
            try:
                self._toast.destroy()
            except tk.TclError:
                pass
        toast = tk.Toplevel(self.root)
        self._toast = toast
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        frame = tk.Frame(
            toast,
            background="#17212b",
            padx=18,
            pady=13,
            highlightthickness=1,
            highlightbackground="#3d5266",
        )
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text="黑流树海奖励采集器",
            background="#17212b",
            foreground="#7bdcb5",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            frame,
            text=message,
            background="#17212b",
            foreground="white",
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(4, 0))
        toast.update_idletasks()
        width = max(330, toast.winfo_reqwidth())
        height = toast.winfo_reqheight()
        x = toast.winfo_screenwidth() - width - 24
        y = toast.winfo_screenheight() - height - 54
        toast.geometry(f"{width}x{height}+{x}+{y}")
        toast.lift()
        toast.after(2400, self._close_toast)

    def _close_toast(self) -> None:
        if self._toast is None:
            return
        try:
            self._toast.destroy()
        except tk.TclError:
            pass
        self._toast = None

    def _present_root(self) -> None:
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(
            900,
            lambda: self.root.attributes("-topmost", False),
        )

    def _review(self, pending: PendingBattle) -> None:
        self._set_phase("review")
        self._present_root()
        default_location = (
            LOCATION_NAMES.get(pending.location_context)
            or self.location_var.get()
        )
        default_combat = (
            COMBAT_NAMES.get(pending.combat_context)
            or self.combat_var.get()
        )
        dialog = ReviewDialog(
            self.root,
            pending,
            defaults={
                "source_floor": (
                    pending.source_floor or self.floor_var.get()
                ),
                "location_context": default_location,
                "combat_context": default_combat,
            },
            topmost=self.topmost_var.get(),
        )
        self.root.wait_window(dialog.window)
        if dialog.record is None:
            if self.live.running:
                self._set_phase("monitoring")
            return
        self.store.append(dialog.record)
        self.floor_var.set(dialog.record.source_floor)
        self.location_var.set(
            LOCATION_NAMES[dialog.record.location_context]
        )
        self.combat_var.set(
            COMBAT_NAMES[dialog.record.combat_context]
        )
        self.count_var.set(
            f"已保存样本：{len(self.store.read_all())}"
        )
        self.status_var.set(
            f"已保存：{dialog.record.stage_name or dialog.record.sample_id}"
        )
        if self.live.running:
            self._set_phase("monitoring")

    def _close(self) -> None:
        self.live.stop()
        self.root.destroy()


class ReviewDialog:
    def __init__(
        self,
        parent: tk.Tk,
        pending: PendingBattle,
        defaults: dict[str, str],
        topmost: bool,
    ) -> None:
        self.pending = pending
        self.record: RewardRecord | None = None
        self.window = tk.Toplevel(parent)
        self._topmost = topmost
        self._presented = False
        self.window.title("确认本场战斗奖励")
        self.window.geometry("720x760")
        self.window.minsize(680, 680)
        if topmost:
            self.window.attributes("-topmost", True)
        self.window.transient(parent)
        self._build(defaults)
        self.window.grab_set()
        self.window.after(20, self._present)
        self.window.after(350, self._present)

    def _present(self) -> None:
        if not self.window.winfo_exists():
            return
        self.window.deiconify()
        self.window.state("normal")
        self.window.lift()
        if self._topmost:
            self.window.attributes("-topmost", True)
        self.window.focus_force()
        if not self._presented:
            self.window.bell()
            self._presented = True

    def _build(self, defaults: dict[str, str]) -> None:
        outer = ttk.Frame(self.window, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text="确认本场战斗",
            font=("Microsoft YaHei UI", 16, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(
            outer,
            text="自动识别只是预填；确认后才会写入统计。",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 12))

        self.floor = tk.StringVar(value=defaults["source_floor"])
        self.location = tk.StringVar(value=defaults["location_context"])
        self.combat = tk.StringVar(value=defaults["combat_context"])
        self.stage = tk.StringVar(value=self.pending.stage_name)
        self.command_xp = tk.StringVar(
            value=(
                str(self.pending.battle_command_xp)
                if self.pending.battle_command_xp is not None
                else ""
            )
        )
        normal_ingots = self.pending.normal_reward_ingots
        if (
            normal_ingots is None
            and self.pending.unowned_wealth_ingots is None
        ):
            normal_ingots = self.pending.reward_ingots
        self.normal_ingots = tk.StringVar(
            value=str(normal_ingots or 0)
        )
        self.unowned_ingots = tk.StringVar(
            value=str(self.pending.unowned_wealth_ingots or 0)
        )
        self.hope = tk.StringVar(value="0")
        self.tickets = tk.StringVar(
            value=str(self.pending.reward_tickets or 0)
        )
        self.collectibles = tk.StringVar(
            value=str(self.pending.reward_collectibles or 0)
        )
        self.parts = tk.StringVar(
            value=str(self.pending.reward_parts or 0)
        )
        self.bonus_parts = tk.StringVar(
            value=str(self.pending.bonus_parts)
        )
        self.bonus = tk.StringVar(value=BONUS_NAMES["none"])
        self.bonus_details = tk.StringVar()
        self.xp_multiplier = tk.StringVar(value="1.2")
        self.ingot_multiplier = tk.StringVar(value="1.0")
        self.notes = tk.StringVar()

        self._combo(
            outer,
            2,
            "来源层数",
            self.floor,
            ("1", "2", "3", "4", "5", "6", "未知"),
        )
        self._combo(
            outer,
            3,
            "所在环境",
            self.location,
            tuple(LOCATION_NAMES.values()),
        )
        self._combo(
            outer,
            4,
            "战斗类型",
            self.combat,
            tuple(COMBAT_NAMES.values()),
        )
        self._entry(outer, 5, "关卡名称", self.stage)
        self._entry(outer, 6, "本次指挥经验", self.command_xp)

        ttk.Separator(outer).grid(
            row=7,
            column=0,
            columnspan=4,
            sticky="ew",
            pady=12,
        )
        ttk.Label(
            outer,
            text="实际获得资源",
            font=("Microsoft YaHei UI", 11, "bold"),
        ).grid(row=8, column=0, columnspan=4, sticky="w")
        self._number_pair(
            outer,
            9,
            "普通源石锭",
            self.normal_ingots,
            "无主的财富源石锭",
            self.unowned_ingots,
        )
        self._number_pair(
            outer,
            10,
            "希望",
            self.hope,
            "招募券",
            self.tickets,
        )
        self._number_pair(
            outer,
            11,
            "收藏品",
            self.collectibles,
            "节点奖励零件",
            self.parts,
        )
        ttk.Label(
            outer,
            text="额外效果零件",
        ).grid(row=12, column=0, sticky="w", pady=4)
        ttk.Entry(
            outer,
            textvariable=self.bonus_parts,
            width=12,
        ).grid(row=12, column=1, sticky="ew", padx=(10, 18), pady=4)
        parts_total = self.pending.parts_total or 0
        parts_details = (
            self.pending.parts_bonus_details or "未识别具体来源"
        )
        ttk.Label(
            outer,
            text=(
                f"零件箱总变化：{parts_total}；"
                f"额外来源：{parts_details}"
            ),
            foreground="#555555",
            wraplength=300,
        ).grid(
            row=12,
            column=2,
            columnspan=2,
            sticky="w",
            pady=4,
        )

        ttk.Separator(outer).grid(
            row=13,
            column=0,
            columnspan=4,
            sticky="ew",
            pady=12,
        )
        self._combo(
            outer,
            14,
            "额外来源",
            self.bonus,
            tuple(BONUS_NAMES.values()),
        )
        self._entry(outer, 15, "额外来源详情", self.bonus_details)
        self._number_pair(
            outer,
            16,
            "经验倍率",
            self.xp_multiplier,
            "源石锭倍率",
            self.ingot_multiplier,
        )
        self._entry(outer, 17, "人工备注", self.notes)

        visible = "、".join(self.pending.visible_reward_names) or "未识别"
        ttk.Label(
            outer,
            text=f"界面展示：{visible}",
            wraplength=640,
            foreground="#444444",
        ).grid(row=18, column=0, columnspan=4, sticky="w", pady=(12, 4))
        evidence = "；".join(self.pending.context_evidence) or "使用手动预设"
        automatic_type = COMBAT_NAMES.get(
            self.pending.combat_context,
            "未自动识别",
        )
        ttk.Label(
            outer,
            text=(
                f"自动节点类型：{automatic_type}；"
                f"识别依据：{evidence}"
            ),
            wraplength=640,
            foreground="#555555",
        ).grid(row=19, column=0, columnspan=4, sticky="w", pady=(0, 4))

        screenshot_frame = ttk.Frame(outer)
        screenshot_frame.grid(
            row=20,
            column=0,
            columnspan=4,
            sticky="w",
        )
        all_images = (
            self.pending.settlement_screenshots
            + self.pending.reward_screenshots
        )
        if all_images:
            ttk.Button(
                screenshot_frame,
                text=f"查看证据截图（{len(all_images)}）",
                command=lambda: os.startfile(str(Path(all_images[0]).parent)),
            ).pack(side="left")

        buttons = ttk.Frame(outer)
        buttons.grid(
            row=21,
            column=0,
            columnspan=4,
            sticky="e",
            pady=(20, 0),
        )
        ttk.Button(
            buttons,
            text="放弃本条",
            command=self.window.destroy,
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="确认并保存",
            command=self._save,
        ).pack(side="left", padx=(10, 0))
        outer.columnconfigure(1, weight=1)
        outer.columnconfigure(3, weight=1)

    @staticmethod
    def _combo(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row,
            column=0,
            sticky="w",
            pady=4,
        )
        ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
        ).grid(
            row=row,
            column=1,
            columnspan=3,
            sticky="ew",
            padx=(10, 0),
            pady=4,
        )

    @staticmethod
    def _entry(
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row,
            column=0,
            sticky="w",
            pady=4,
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            columnspan=3,
            sticky="ew",
            padx=(10, 0),
            pady=4,
        )

    @staticmethod
    def _number_pair(
        parent: ttk.Frame,
        row: int,
        left_label: str,
        left_var: tk.StringVar,
        right_label: str,
        right_var: tk.StringVar | None,
    ) -> None:
        ttk.Label(parent, text=left_label).grid(
            row=row,
            column=0,
            sticky="w",
            pady=4,
        )
        ttk.Entry(
            parent,
            textvariable=left_var,
            width=12,
        ).grid(row=row, column=1, sticky="ew", padx=(10, 18), pady=4)
        if right_var is not None:
            ttk.Label(parent, text=right_label).grid(
                row=row,
                column=2,
                sticky="w",
                pady=4,
            )
            ttk.Entry(
                parent,
                textvariable=right_var,
                width=12,
            ).grid(row=row, column=3, sticky="ew", padx=(10, 0), pady=4)

    @staticmethod
    def _int(value: str, field: str) -> int:
        try:
            parsed = int(value or "0")
        except ValueError as exc:
            raise ValueError(f"{field}必须是整数") from exc
        if parsed < 0:
            raise ValueError(f"{field}不能为负数")
        return parsed

    @staticmethod
    def _float(value: str, field: str) -> float:
        try:
            parsed = float(value or "1")
        except ValueError as exc:
            raise ValueError(f"{field}必须是数字") from exc
        if parsed <= 0:
            raise ValueError(f"{field}必须大于0")
        return parsed

    def _save(self) -> None:
        try:
            command_xp = (
                self._int(self.command_xp.get(), "指挥经验")
                if self.command_xp.get().strip()
                else None
            )
            normal_ingots = self._int(
                self.normal_ingots.get(),
                "普通源石锭",
            )
            unowned_ingots = self._int(
                self.unowned_ingots.get(),
                "无主的财富源石锭",
            )
            record = RewardRecord(
                sample_id=self.pending.sample_id,
                captured_at=self.pending.started_at,
                source_floor=self.floor.get(),
                location_context=LOCATION_IDS[self.location.get()],
                combat_context=COMBAT_IDS[self.combat.get()],
                stage_name=self.stage.get().strip(),
                command_xp=command_xp,
                originium_ingots=normal_ingots + unowned_ingots,
                normal_reward_ingots=normal_ingots,
                unowned_wealth_ingots=unowned_ingots,
                hope=self._int(self.hope.get(), "希望"),
                recruitment_tickets=self._int(
                    self.tickets.get(),
                    "招募券",
                ),
                collectibles=self._int(
                    self.collectibles.get(),
                    "收藏品",
                ),
                parts=self._int(self.parts.get(), "零件"),
                bonus_parts=self._int(
                    self.bonus_parts.get(),
                    "额外效果零件",
                ),
                parts_total=(
                    self._int(self.parts.get(), "零件")
                    + self._int(
                        self.bonus_parts.get(),
                        "额外效果零件",
                    )
                ),
                parts_bonus_details=self.pending.parts_bonus_details,
                bonus_source=BONUS_IDS[self.bonus.get()],
                bonus_details=self.bonus_details.get().strip(),
                command_xp_multiplier=self._float(
                    self.xp_multiplier.get(),
                    "经验倍率",
                ),
                ingot_multiplier=self._float(
                    self.ingot_multiplier.get(),
                    "源石锭倍率",
                ),
                displayed_reward_names=tuple(
                    self.pending.visible_reward_names
                ),
                settlement_screenshots=tuple(
                    self.pending.settlement_screenshots
                ),
                reward_screenshots=tuple(
                    self.pending.reward_screenshots
                ),
                ocr_text="\n\n---\n\n".join(self.pending.ocr_text),
                reviewer_notes=self.notes.get().strip(),
            )
        except (KeyError, ValueError) as exc:
            messagebox.showerror("无法保存", str(exc), parent=self.window)
            return
        self.record = record
        self.window.destroy()


def run_app(project_root: Path) -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    CollectorApp(root, project_root)
    root.mainloop()
