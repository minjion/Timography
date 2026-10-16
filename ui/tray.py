import pystray
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

class TrayManager:
    def __init__(self, root, widget, main_window_callback, add_event_callback, quit_callback, routines_callback=None, dispatch=None):
        self.root = root
        self.dispatch = dispatch or (lambda callback: root.after(0, callback))
        self.widget = widget
        self.main_window_callback = main_window_callback
        self.add_event_callback = add_event_callback
        self.quit_callback = quit_callback
        self.routines_callback = routines_callback
        self.icon = None

    def _create_icon_image(self) -> Image.Image:
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Draw calendar shape
        draw.rounded_rectangle([4, 4, 60, 60], radius=8, fill='#58a6ff')
        # White header bar
        draw.rectangle([4, 4, 60, 20], fill='#f0f6fc')

        # Day number
        day = str(datetime.now().day)
        try:
            font = ImageFont.truetype("segoeui.ttf", 24)
        except OSError:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0,0), day, font=font)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text(((64-tw)/2, 22 + (38-th)/2), day, fill='white', font=font)
        return img

    def _toggle_widget(self, icon, item):
        self.dispatch(self.widget.toggle)

    def _open_main(self, icon, item):
        self.dispatch(self.main_window_callback)

    def _open_routines(self, icon, item):
        if self.routines_callback:
            self.dispatch(self.routines_callback)

    def _add_event(self, icon, item):
        self.dispatch(self.add_event_callback)

    def _quit(self, icon, item):
        self.dispatch(self.quit_callback)

    def run(self):
        image = self._create_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("Open Planner", self._open_main, default=True),
            pystray.MenuItem("Show/Hide Desktop Widget", self._toggle_widget),
            pystray.MenuItem("Manage Routines", self._open_routines),
            pystray.MenuItem("Add Event", self._add_event),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )
        self.icon = pystray.Icon("Timography", image, "Timography", menu)
        self.icon.run()

    def stop(self):
        if self.icon:
            self.icon.stop()
