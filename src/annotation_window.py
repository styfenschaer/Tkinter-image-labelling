import tkinter as tk
from functools import partial

import pyautogui
from PIL import Image, ImageOps, ImageTk


def canvas_size(canv):
    return int(canv["width"]), int(canv["height"])


def sign(num):
    return 1 if num >= 0 else -1


def noop(*args, **kwargs):
    ...


class Rectangle:
    _coords = ("x1", "y1", "x2", "y2")

    _config = dict(
        outline="#e95620",
        width=1,
    )

    def __init__(self, canv, **kwargs):
        self.canv = canv
        self._id = None
        for c in self._coords:
            var = tk.DoubleVar(canv, kwargs.get(c, 0))
            var.trace("w", self.draw)
            setattr(self, c, var)

    def set(self, **kwargs):
        for c in self._coords:
            var = getattr(self, c)
            var.set(kwargs.get(c, var.get()))

    def get(self):
        return tuple(getattr(self, c).get() for c in self._coords)

    def delete(self):
        self.canv.delete(self._id)

    def draw(self, *args, **kwargs):
        self.canv.delete(self._id)
        self._id = self.canv.create_rectangle(*self.get(), **self._config)

    def duplicate(self, canv, x, y, scale):
        x1, y1, x2, y2 = self.get()
        w2, h2 = canvas_size(canv)
        rw, rh = (x2-x1), (y2-y1)

        xz1 = x1 - (x-w2/2)
        yz1 = y1 - (y-h2/2)
        xz2 = xz1 + rw
        yz2 = yz1 + rh

        xz1 -= (w2/2 - xz1)*(scale-1)
        yz1 -= (h2/2 - yz1)*(scale-1)
        xz2 -= (w2/2 - xz2)*(scale-1)
        yz2 -= (h2/2 - yz2)*(scale-1)

        canv.create_rectangle(xz1, yz1, xz2, yz2, **self._config)

    def spotlight(self):
        self.canv.delete(self._id)
        config = self._config.copy()
        config.update(dict(width=self._config["width"] + 2))
        self._id = self.canv.create_rectangle(*self.get(), **config)


class Reticle:

    _config = dict(
        fill="#e05194",
        width=1,
    )

    def __init__(self, canv):
        self.canv = canv

        self._idh = None
        self.cent_h = tk.DoubleVar(canv, 0)
        self.cent_h.trace("w", self.draw)

        self._idv = None
        self.cent_v = tk.DoubleVar(canv, 0)
        self.cent_v.trace("w", self.draw)

    def get(self):
        w, h = canvas_size(self.canv)
        cent_h, cent_v = self.cent_h.get(), self.cent_v.get()
        line_h = (cent_h - w, cent_v, cent_h + w, cent_v)
        line_v = (cent_h, cent_v - h, cent_h, cent_h + h)
        return line_h, line_v

    def set(self, x, y):
        self.cent_h.set(x)
        self.cent_v.set(y)

    def delete(self):
        self.canv.delete(self._idv, self._idh)

    def draw(self, *args, **kwargs):
        line_h, line_v = self.get()

        self.canv.delete(self._idh)
        self._idh = self.canv.create_line(line_h, **self._config)
        self.canv.delete(self._idv)
        self._idv = self.canv.create_line(line_v, **self._config)

    def duplicate(self, canv):
        w2, h2 = canvas_size(canv)
        line_h = (w2/2 - w2, h2/2, w2/2 + w2, h2/2)
        line_v = (w2/2, h2/2 - h2, w2/2, h2/2 + h2)

        self.canv.delete(self._idh)
        self._idh = canv.create_line(line_h, **self._config)
        self.canv.delete(self._idv)
        self._idv = canv.create_line(line_v, **self._config)


class ZoomCanvas(tk.Canvas):

    _delta_zoom = 0.1
    _min_zoom = 0.1
    _max_zoom = 5.0
    _init_zoom = 2.0

    _config = dict(
        highlightthickness=0,
    )

    def __init__(self, master, width=200, height=200):
        super().__init__(master, width=width, height=height,  **self._config)

        self.bind("<MouseWheel>", self._on_wheel)
        self.zoom = self._init_zoom

    def _on_wheel(self, e):
        zoom = self.zoom + sign(e.delta) * self._delta_zoom
        self.zoom = sorted((self._min_zoom, zoom, self._max_zoom))[1]

    def insert_image(self, image, x, y):
        w, h = canvas_size(self)
        image = image.crop((
            x - w/2/self.zoom,
            y - h/2/self.zoom,
            x + w/2/self.zoom,
            y + h/2/self.zoom,
        ))
        image = image.resize((w, h))
        self.image = ImageTk.PhotoImage(image)
        self.create_image((0, 0), anchor=tk.NW, image=self.image)


def _if_bool(mode, bool_):
    def decorator(fn):
        def inner(self, *args, **kwargs):
            if getattr(self, mode) == bool_:
                return
            return fn(self, *args, **kwargs)
        return inner
    return decorator


if_true = partial(_if_bool, bool_=False)
if_false = partial(_if_bool, bool_=True)


def switch_bool(mode):
    def decorator(fn):
        def inner(self, *args, **kwargs):
            setattr(self, mode, not getattr(self, mode, False))
            return fn(self, *args, **kwargs)
        return inner
    return decorator


class AnnotationCanvas(tk.Canvas):

    _step_size = 2
    _delta_step_size = 1
    _min_step_size = 1
    _max_step_size = 20

    _config = dict(
        highlightthickness=0,
    )

    def __init__(self, master, width=600, height=600, width_zoom=200, height_zoom=200):
        super().__init__(master, width=width, height=height, **self._config)

        self.bind("<Motion>", self._on_hover)
        self.bind('<Double-Button-1>', self._on_double_click)
        self.bind('<KeyPress>', self._on_keypress)
        self.bind('<KeyRelease>', self._on_keyrelease)
        self.bind("<1>", lambda e: self.focus_set())

        self._rec_ids = []
        self._rec_idx = -1
        self._anno_mode = False

        self._reticle_idx = Reticle(self)
        self._zoom_window = ZoomCanvas(self, width_zoom, height_zoom)

    @if_true("_anno_mode")
    def _move_rec(self, e, x, y):
        pyautogui.moveRel(x*self._step_size, y*self._step_size)
        rec = self._rec_ids[self._rec_idx]
        coords = dict(
            x1=rec.x1.get() + x*self._step_size,
            y1=rec.y1.get() + y*self._step_size,
            x2=rec.x2.get() + x*self._step_size,
            y2=rec.y2.get() + y*self._step_size,
        )
        rec.set(**coords)

    @if_true("_anno_mode")
    def _move_vert(self, e, x, y):
        pyautogui.moveRel(x*self._step_size, y*self._step_size)

    @if_true("_anno_mode")
    def _escape(self, e):
        self._on_double_click(e)
        self._rec_ids.pop(self._rec_idx).delete()

    @if_true("_rec_ids")
    @if_false("_anno_mode")
    def _delete(self, e):
        self._rec_ids.pop(self._rec_idx).delete()

    @if_true("_rec_ids")
    @if_true("_anno_mode")
    def _on_hover_rectangle(self, e):
        self._rec_ids[self._rec_idx].set(x2=e.x, y2=e.y)

    def _on_hover_cross(self, e):
        self._reticle_idx.set(x=e.x, y=e.y)

    def _on_hover(self, e):
        self._on_hover_rectangle(e)
        self._on_hover_cross(e)

    @switch_bool("_anno_mode")
    @if_true("_anno_mode")
    def _on_double_click(self, e):
        rec_id = Rectangle(self, x1=e.x, y1=e.y, x2=e.x, y2=e.y)
        self._rec_ids.append(rec_id)
        self._rec_idx = -1

    def _update_step(self, e, sign):
        step = self._step_size + sign * self._delta_step_size
        self._step_size = sorted(
            (self._min_step_size, step, self._max_step_size))[1]

    def _zoom_on(self, e):
        self._win = self.create_window(e.x, e.y, window=self._zoom_window)
        self._zoom_window.insert_image(self._image, e.x, e.y)

        for r in self._rec_ids:
            r.duplicate(self._zoom_window, e.x, e.y, self._zoom_window.zoom)

        self._reticle_idx.duplicate(self._zoom_window)
        self._reticle_idx.set(x=e.x, y=e.y)

    def _zoom_off(self, e):
        self.delete(self._win)

    @if_true("_rec_ids")
    def _switch_rectangle(self, e, val):
        self._rec_idx += val
        self._rec_idx %= len(self._rec_ids)

        for r in self._rec_ids:
            r.draw()
        self._rec_ids[self._rec_idx].spotlight()

    _on_keypress_dct = {
        "Down": partial(_move_vert, x=0, y=1),
        "Up": partial(_move_vert, x=0, y=-1),
        "Left": partial(_move_vert, x=-1, y=0),
        "Right": partial(_move_vert, x=1, y=0),
        "d": partial(_move_rec, x=1, y=0),
        "a": partial(_move_rec, x=-1, y=0),
        "s": partial(_move_rec, x=0, y=1),
        "w": partial(_move_rec, x=0, y=-1),
        "z": _zoom_on,
        "Return": _on_double_click,
        "Escape": _escape,
        "q": _delete,
        "m": switch_bool("_anno_mode")(noop),
        "Prior": partial(_update_step, sign=1),
        "Next": partial(_update_step, sign=-1),
        "x": partial(_switch_rectangle, val=1),
        "y": partial(_switch_rectangle, val=-1),
    }

    def _on_keypress(self, e):
        fn = self._on_keypress_dct.get(e.keysym, noop)
        return fn(self, e)

    _on_keyrelease_dct = {
        "z": _zoom_off,
    }

    def _on_keyrelease(self, e):
        fn = self._on_keyrelease_dct.get(e.keysym, noop)
        return fn(self, e)

    def insert_image(self, path):
        for r in self._rec_ids:
            r.delete()
        self._rec_ids = []

        image = Image.open(path)
        self._image = ImageOps.contain(image, canvas_size(self))
        self.image = ImageTk.PhotoImage(self._image)
        self.create_image((0, 0), anchor=tk.NW, image=self.image)

        width, height = self._image.size
        self.config(width=width, height=height)


if __name__ == "__main__":
    from pathlib import Path

    root = tk.Tk()
    root.geometry("1920x1080")
    canv = AnnotationCanvas(root, width=1820, height=980,
                            width_zoom=400, height_zoom=400)
    canv.pack()

    directory = Path(__file__).parent.parent / Path("images")
    canv.insert_image(directory / Path("image01.jpg"))

    root.mainloop()
