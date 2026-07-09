from app.routers.terminal import _set_winsize


def test_set_winsize_calls_ioctl_with_terminal_size(monkeypatch):
    captured = {}

    def fake_ioctl(fd, op, winsize):
        captured["fd"] = fd
        captured["op"] = op
        captured["winsize"] = winsize

    monkeypatch.setattr("app.routers.terminal.fcntl.ioctl", fake_ioctl)

    _set_winsize(10, 24, 80)

    assert captured["fd"] == 10
    assert len(captured["winsize"]) == 8
