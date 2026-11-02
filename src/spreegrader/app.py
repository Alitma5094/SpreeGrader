"""
A desktop grader for Canvs
"""

import asyncio
import os
import platform
import re
import subprocess

import toga
from toga.style.pack import COLUMN, ROW, Pack

import copy
from .auth import OAuth, TokenAuth
from .canvas import Canvas, CanvasError
from .config import Config
from .institution import INSTITUTION

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "SpreeGraderSubmissions")

def safe_name(text):
    return re.sub(r"[^\w\-. ]+", "_", text).strip() or "unnamed"
 
 
def open_file(path):
    system = platform.system()
    if system == "Windows":
        os.startfile(path)
    elif system == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def set_choices(box: toga.Selection, names, placeholder=None):
    """Fill a Selection with rows carrying an `idx` into the source list.
    The optional placeholder row has idx == -1 (Selection can't be empty)."""
    items = []
    if placeholder:
        items.append({"title": placeholder, "idx": -1})
    items.extend({"title": n, "idx": i} for i, n in enumerate(names))
    box.items = items


def selected_idx(box: toga.Selection) -> int:
    value = box.value
    return value.idx if value is not None else -1


def form_row(label_text, *widgets, label_width=90):
    label = toga.Label(
        label_text,
        style=Pack(width=label_width, text_align="right", margin_right=6),
    )
    return toga.Box(
        children=[label, *widgets],
        style=Pack(direction=ROW, align_items="center", margin_top=3),
    )


class SpreeGrader(toga.App):
    def startup(self):
        self.config = Config(self.paths.config / "config.json")
        self.canvas = None
        self._assignments_for = None
        self.courses = []
        self.assignments = []
        self.user = None
        self.entries = []
        self.current = None
        self.course_id = None
        self.assignment_id = None
        self._assignments_for = None

        main_box = toga.Box()

        # self.main_window = toga.MainWindow(title=self.formal_name, size=(980, 680))
        # self.main_window.content = self._build_ui()
        # self.main_window.show()
        self.main_window = toga.MainWindow(title=self.formal_name, size=(980, 680))
        self.main_window.content = toga.Box(children=[toga.Label("Loading…")])
        self.main_window.show()
        # TODO: add_background_task depricated
        # self.add_background_task(self._sign_in)
        self.on_running = self._restore_session

    def _build_ui(self):
        self.course_box = toga.Selection(
            items=[],
            accessor="title",
            on_change=self.on_course_selected,
            style=Pack(flex=1),
        )
        self.assign_box = toga.Selection(items=[], accessor="title", style=Pack(flex=1))
        set_choices(self.course_box, [], "Select a course…")
        set_choices(self.assign_box, [], "Select an assignment…")

        self.dir_input = toga.TextInput(value=self.config.data["download_dir"] or DEFAULT_DOWNLOAD_DIR, style=Pack(flex=1))
        browse_btn = toga.Button(
            "Browse…",
             on_press=self.browse,
            style=Pack(margin_left=6),
        )

        self.download_btn = toga.Button(
            "Download submissions & start grading",
            on_press=self.load_submissions
        )

        select_frame = toga.Box(
            children=[
                toga.Label("Pick course & assignment", style=Pack(font_weight="bold")),
                form_row("Course:", self.course_box),
                form_row("Assignment:", self.assign_box),
                form_row("Save to:", self.dir_input, browse_btn),
                toga.Box(
                    children=[toga.Box(style=Pack(flex=1)), self.download_btn],
                    style=Pack(direction=ROW, margin_top=3),
                ),
            ],
            style=Pack(direction=COLUMN, margin=8),
        )

        self.status_label = toga.Label(
            "Logging in...",
            style=Pack(margin_left=8, margin_right=8, text_align="right"),
        )

        # --- left: submission list ---
        self.table = toga.Table(
            headings=[" ", "Student", "Grade"],
            accessors=["status", "student", "grade"],
            data=[],
            multiple_select=False,
            on_select=self.on_row_selected,
            style=Pack(width=320, flex=1),
        )

        # --- right: grading panel ---
        self.student_label = toga.Label(
            "—", style=Pack(font_size=14, font_weight="bold")
        )
        self.info_label = toga.Label("", style=Pack(color="#666666", margin_bottom=6))

        self.file_box = toga.Selection(items=[], accessor="title", style=Pack(flex=1))
        open_btn = toga.Button(
            "Open file",
               on_press=self.open_clicked,
            style=Pack(margin_left=6),
        )

        self.grade_input = toga.TextInput(style=Pack(width=100))
        grade_hint = toga.Label(
            "(points, %, or letter)", style=Pack(color="#666666", margin_left=6)
        )

        self.comment_input = toga.MultilineTextInput(style=Pack(flex=1, height=140))
        self.prev_comments = toga.MultilineTextInput(
            readonly=True, style=Pack(flex=1, height=80)
        )

        buttons = toga.Box(
            children=[
                toga.Button(
                    "◀ Previous",
                    on_press=self.prev_clicked,
                    style=Pack(margin_left=3),
                ),
                toga.Button(
                    "Next ▶",
                    on_press=self.next_clicked,
                    style=Pack(margin_left=3),
                ),
                toga.Button(
                    "Save grade to Canvas",
                    on_press=self.save_clicked,
                    style=Pack(margin_left=3),
                ),
                toga.Button(
                    "Save & next ▶",
                    on_press=self.save_next_clicked,
                    style=Pack(margin_left=3),
                ),
            ],
            style=Pack(direction=ROW, margin_top=8),
        )
        button_row = toga.Box(
            children=[toga.Box(style=Pack(flex=1)), buttons],
            style=Pack(direction=ROW),
        )

        self.auto_open = toga.Switch(
            "Automatically open the file when I move to a student",
            value=True,
            style=Pack(margin_top=6),
        )

        right = toga.Box(
            children=[
                self.student_label,
                self.info_label,
                form_row("Submission:", self.file_box, open_btn),
                form_row("Grade:", self.grade_input, grade_hint),
                form_row("Comment:", self.comment_input),
                form_row("Previous comments:", self.prev_comments),
                button_row,
                self.auto_open,
            ],
            style=Pack(direction=COLUMN, flex=1, margin_left=8),
        )

        grading = toga.Box(
            children=[self.table, right],
            style=Pack(direction=ROW, flex=1, margin=8),
        )

        return toga.Box(
            children=[select_frame, self.status_label, grading],
            style=Pack(direction=COLUMN),
        )

    def set_status(self, text):
        self.status_label.text = str(text)

    def _status_threadsafe(self, text):
        """Call from worker threads."""
        self.loop.call_soon_threadsafe(self.set_status, text)

    # -------------------------------------------------------------- sign in
        # ------------------------------------------------------------- sign in
    def _make_oauth(self):
        i = INSTITUTION
        return OAuth(
            i["base_url"], i["client_id"], i["client_secret"],
            self.config.data["oauth"], self.config.save,
            port=i.get("redirect_port", 53682),
        )

    async def _restore_session(self, app=None, **kwargs):
        cfg = self.config.data
        auth = base_url = None
        if cfg["auth_method"] == "token" and cfg["api_key"] and cfg["base_url"]:
            auth, base_url = TokenAuth(cfg["api_key"]), cfg["base_url"]
        elif cfg["auth_method"] == "oauth" and INSTITUTION and cfg["oauth"]["refresh_token"]:
            auth, base_url = self._make_oauth(), INSTITUTION["base_url"]

        if auth is None:
            self.show_login()
            return
        await self._start_session(auth, base_url, on_fail_message="Session expired. Please sign in again.")

    async def _start_session(self, auth, base_url, on_fail_message=None):
        canvas = Canvas(base_url, auth)
        try:
            user = await asyncio.to_thread(canvas.get_current_user)
        except Exception as e:  # noqa: BLE001
            if isinstance(e, CanvasError) and e.status_code == 401:
                self.config.clear_credentials()
            self.show_login(on_fail_message or f"Sign-in failed: {e}")
            return False
        self.canvas, self.user = canvas, user
        self.main_window.content = self._build_ui()
        self.set_status(f"Welcome {user['name']}")
        await self._load_courses()
        return True

    # --------------------------------------------------------------- login UI
    def show_login(self, message=""):
        cfg = self.config.data
        inst = INSTITUTION
        self.login_status = toga.Label(message, style=Pack(margin_top=8))
        children = [toga.Label("Sign in to Canvas", style=Pack(font_size=14, font_weight="bold"))]

        if inst:
            self.oauth_btn = toga.Button(
                f"Sign in with {inst['name']}", on_press=self.oauth_clicked,
                style=Pack(margin_top=8),
            )
            children.append(self.oauth_btn)

        if not inst or inst.get("allow_token_login"):
            self.url_input = toga.TextInput(value=cfg["base_url"] or "https://", style=Pack(flex=1))
            self.key_input = toga.PasswordInput(style=Pack(flex=1))
            self.token_btn = toga.Button("Sign in with access token", on_press=self.token_clicked)
            if not inst:
                children.append(form_row("Canvas URL:", self.url_input, label_width=110))
            children += [
                form_row("Access token:", self.key_input, label_width=110),
                toga.Box(children=[toga.Box(style=Pack(flex=1)), self.token_btn],
                         style=Pack(direction=ROW, margin_top=6)),
            ]
        children.append(self.login_status)
        self.main_window.content = toga.Box(
            children=children, style=Pack(direction=COLUMN, margin=20, width=520)
        )

    def _set_login_busy(self, busy, text=""):
        for name in ("oauth_btn", "token_btn"):
            btn = getattr(self, name, None)
            if btn is not None:
                btn.enabled = not busy
        self.login_status.text = text

    @staticmethod
    def _normalize_url(url):
        url = url.strip().rstrip("/")
        if url and "://" not in url:
            url = "https://" + url
        return url

    async def token_clicked(self, widget, **kwargs):
        base_url = INSTITUTION["base_url"] if INSTITUTION else self._normalize_url(self.url_input.value)
        token = (self.key_input.value or "").strip()
        if not base_url or not token:
            self.login_status.text = "Enter a Canvas URL and an access token."
            return
        self._set_login_busy(True, "Signing in…")
        ok = await self._start_session(TokenAuth(token), base_url)
        if ok:  # only persist credentials that actually worked
            self.config.data.update(base_url=base_url, auth_method="token", api_key=token)
            self.config.save()

    async def oauth_clicked(self, widget, **kwargs):
        auth = self._make_oauth()
        self._set_login_busy(True, "Finish signing in in your browser…")
        try:
            await asyncio.to_thread(auth.authorize)
        except Exception as e:  # noqa: BLE001
            self._set_login_busy(False, str(e))
            return
        self.config.data.update(base_url=INSTITUTION["base_url"], auth_method="oauth", api_key="")
        self.config.save()
        await self._start_session(auth, INSTITUTION["base_url"])

    def sign_out(self, widget=None, **kwargs):
        self.config.clear_credentials()
        self.canvas = self.user = None
        self.courses, self.assignments, self.entries = [], [], []
        self.current = None
        self._assignments_for = None
        self.show_login()

    async def _load_courses(self):
        try:
            result = await asyncio.to_thread(self.canvas.get_courses)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Failed to get courses: {e}")
            return

        self.courses = sorted(result, key=lambda c: c.get("name", ""))
        set_choices(
            self.course_box,
            [c.get("name", str(c["id"])) for c in self.courses],
            "Select a course…",
        )
        if len(self.courses) == 1:
            self.course_box.value = self.course_box.items[1]
            await self._load_assignments(0)

    # ---------------------------------------------------------- assignments
    async def on_course_selected(self, widget, **kwargs):
        idx = selected_idx(self.course_box)
        if idx >= 0:
            await self._load_assignments(idx)

    async def _load_assignments(self, idx):
        course = self.courses[idx]
        if self._assignments_for == course["id"]:
            return  # already loaded (guards against double change events)
        self.set_status("Loading assignments…")
        try:
            result = await asyncio.to_thread(self.canvas.get_assignments, course["id"])
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Failed to get assignments: {e}")
            return
        self._assignments_for = course["id"]
        self.assignments = result
        set_choices(
            self.assign_box,
            [a.get("name", str(a["id"])) for a in result],
            "Select an assignment…",
        )
        self.set_status(f"{len(result)} assignment(s) loaded.")

    # ------------------------------------------------------------ downloads
    async def browse(self, widget, **kwargs):
        path = await self.main_window.dialog(
            toga.SelectFolderDialog(title="Choose download folder")
        )
        if path:
            self.dir_input.value = str(path)

    def _download_all(self, course, assignment, dest_root):
        """Runs in a worker thread. Don't touch widgets in here."""
        all_submissions = self.canvas.get_submissions(course["id"], assignment["id"])
        file_subs = [
            s
            for s in all_submissions
            if s.get("workflow_state") != "unsubmitted" and s.get("attachments")
        ]
        file_subs.sort(
            key=lambda s: (s.get("user") or {}).get("sortable_name", str(s["user_id"]))
        )

        total_files = sum(len(s["attachments"]) for s in file_subs) or 1
        done_files = 0
        entries = []
        for s in file_subs:
            user = s.get("user") or {}
            name = user.get("name") or f"Student {s['user_id']}"
            folder = os.path.join(
                dest_root,
                safe_name(user.get("sortable_name", name)) + f"_{s['user_id']}",
            )
            os.makedirs(folder, exist_ok=True)
            files = []
            for att in s["attachments"]:
                fname = safe_name(
                    att.get("display_name") or att.get("filename") or "file"
                )
                path = os.path.join(folder, fname)
                if not (
                    os.path.exists(path)
                    and os.path.getsize(path) == att.get("size", -1)
                ):
                    self.canvas.download_file(att["url"], path)
                files.append(path)
                done_files += 1
                self._status_threadsafe(
                    f"Downloaded {done_files}/{total_files}: {name}"
                )
            entries.append(
                {
                    "user_id": s["user_id"],
                    "name": name,
                    "files": files,
                    "grade": s.get("grade") or "",
                    "score": s.get("score"),
                    "late": s.get("late", False),
                    "submitted_at": s.get("submitted_at") or "",
                    "comments": [
                        f"{c.get('author_name', '?')}: {c.get('comment', '')}"
                        for c in s.get("submission_comments", [])
                    ],
                    "dirty_grade": None,
                    "draft_comment": "",
                }
            )
        return entries

    async def load_submissions(self, widget=None, **kwargs):
        if not self.user:
            self.set_status("Not signed in")
            return

        course_idx = selected_idx(self.course_box)
        assign_idx = selected_idx(self.assign_box)
        if course_idx < 0 or assign_idx < 0:
            self.set_status("Choose a course and an assignment first")
            return

        course = self.courses[course_idx]
        assignment = self.assignments[assign_idx]
        self.course_id, self.assignment_id = course["id"], assignment["id"]

        dest_root = os.path.join(
            self.dir_input.value,
            safe_name(course.get("name", "course")),
            safe_name(assignment.get("name", "assignment")),
        )
        self.config.data["download_dir"] = self.dir_input.value
        self.config.save()
        os.makedirs(dest_root, exist_ok=True)

        self.set_status("Fetching submission list…")
        self.download_btn.enabled = False
        try:
            result = await asyncio.to_thread(
                self._download_all, course, assignment, dest_root
            )
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Download failed: {e}")
            return
        finally:
            self.download_btn.enabled = True

        self.entries = result
        self.current = None
        self.refresh_submission_list()
        if result:
            self.set_status(f"Done. {len(result)} submission(s) ready.")
            self.select(0)
        else:
            self.set_status("Nothing to grade. No submissions with files were found.")

    # ------------------------------------------------------- submission list
    def _row_data(self, i):
        e = self.entries[i]
        if i == self.current:
            status = "▶"
        elif e["grade"] != "":
            status = "✓"
        else:
            status = ""
        return {
            "status": status,
            "student": e["name"] + (" (late)" if e["late"] else ""),
            "grade": e["grade"],
            "idx": i,
        }

    def refresh_submission_list(self):
        self.table.data = [self._row_data(i) for i in range(len(self.entries))]

    def _refresh_row(self, i):
        if i is None or not (0 <= i < len(self.entries)):
            return
        data = self._row_data(i)
        row = self.table.data[i]
        row.status = data["status"]
        row.student = data["student"]
        row.grade = data["grade"]

    def on_row_selected(self, widget, **kwargs):
        row = widget.selection
        if row is None:
            return
        if row.idx != self.current:
            self.select(row.idx)

    # -------------------------------------------------------------- grading
    def _stash_current(self):
        if self.current is None or self.current >= len(self.entries):
            return
        e = self.entries[self.current]
        e["dirty_grade"] = (self.grade_input.value or "").strip()
        e["draft_comment"] = (self.comment_input.value or "").strip()

    def select(self, idx):
        self._stash_current()
        previous = self.current
        self.current = idx
        e = self.entries[idx]

        self.student_label.text = e["name"]
        bits = [f"Submission {idx + 1} of {len(self.entries)}"]
        if e["submitted_at"]:
            bits.append(
                f"submitted {e['submitted_at'].replace('T', ' ').rstrip('Z')} UTC"
            )
        if e["late"]:
            bits.append("LATE")
        self.info_label.text = " · ".join(bits)

        set_choices(self.file_box, [os.path.basename(p) for p in e["files"]])
        self.grade_input.value = (
            e["dirty_grade"] if e["dirty_grade"] is not None else e["grade"]
        )
        self.comment_input.value = e.get("draft_comment", "")
        self.prev_comments.value = "\n".join(e["comments"]) or "(none)"

        self._refresh_row(previous)
        self._refresh_row(idx)

        if self.auto_open.value:
            self.open_current_file()
        self.grade_input.focus()

    def go(self, delta):
        if self.current is None:
            return
        new = self.current + delta
        if 0 <= new < len(self.entries):
            self.select(new)

    def open_current_file(self):
        if self.current is None:
            return
        e = self.entries[self.current]
        i = max(selected_idx(self.file_box), 0)
        try:
            open_file(e["files"][i])
        except Exception as ex:  # noqa: BLE001
            self.set_status(f"Couldn't open file: {ex}")

    # -------------------------------------------------------- button handlers
    def open_clicked(self, widget, **kwargs):
        self.open_current_file()

    def prev_clicked(self, widget, **kwargs):
        self.go(-1)

    def next_clicked(self, widget, **kwargs):
        self.go(+1)

    async def save_clicked(self, widget, **kwargs):
        await self.save_grade(advance=False)

    async def save_next_clicked(self, widget, **kwargs):
        await self.save_grade(advance=True)

    async def save_grade(self, advance=False):
        if self.current is None:
            return
        self._stash_current()
        idx = self.current
        e = self.entries[idx]
        grade, comment = e["dirty_grade"], e["draft_comment"]

        data = {}
        if grade:
            data["submission[posted_grade]"] = grade
        if comment:
            data["comment[text_comment]"] = comment
        if not data:
            self.set_status("Nothing to save: enter a grade or a comment.")
            return

        self.set_status(f"Saving {e['name']}…")
        try:
            result = await asyncio.to_thread(
                self.canvas.update_submission,
                self.course_id,
                self.assignment_id,
                e["user_id"],
                data,
            )
        except Exception as ex:  # noqa: BLE001
            self.set_status(f"Failed to save: {ex}")
            return

        if grade:
            e["grade"] = result.get("grade") or grade
            e["score"] = result.get("score")
            e["dirty_grade"] = None
        if comment:
            author = (self.user or {}).get("name", "Me")
            e["comments"].append(f"{author}: {comment}")
            e["draft_comment"] = ""
            if self.current == idx:
                self.comment_input.value = ""
                self.prev_comments.value = "\n".join(e["comments"])
        if self.current == idx:
            self.grade_input.value = e["grade"]
        self._refresh_row(idx)
        self.set_status(f"Saved {e['name']}.")

        if advance:
            self.go(+1)


def main():
    return SpreeGrader()
