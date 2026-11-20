"""Windows executable entry point."""
import traceback
import sys

if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--watch-parent":
            from focus_shield.core.website_blocker import watch_parent
            watch_parent(int(sys.argv[2]))
            sys.exit(0)
        from focus_shield.main import main
        main()
    except Exception:
        from tkinter import Tk, messagebox
        root = Tk()
        root.withdraw()
        messagebox.showerror("Pianissimo could not start", traceback.format_exc())
        root.destroy()
