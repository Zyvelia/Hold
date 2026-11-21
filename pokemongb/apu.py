"""Game Boy APU. Enough of the four channels for music and effects."""

from __future__ import annotations

import array

_DUTY = (
    (0, 0, 0, 0, 0, 0, 0, 1),
    (1, 0, 0, 0, 0, 0, 0, 1),
    (1, 0, 0, 0, 0, 1, 1, 1),
    (0, 1, 1, 1, 1, 1, 1, 0),
)
_NOISE_DIV = (8, 16, 32, 48, 64, 80, 96, 112)


class _Pulse:
    def __init__(self):
        self.enabled = False
        self.dac = False
        self.duty = 2
        self.duty_pos = 0
        self.length = 0
        self.length_en = False
        self.volume = 0
        self.env_vol = 0
        self.env_add = False
        self.env_period = 0
        self.env_timer = 0
        self.freq = 0
        self.period = 2048
        self.timer = 2048
        self.sweep_period = 0
        self.sweep_neg = False
        self.sweep_shift = 0
        self.sweep_timer = 0
        self.sweep_en = False
        self.shadow = 0


class _Wave:
    def __init__(self):
        self.enabled = False
        self.dac = False
        self.length = 0
        self.length_en = False
        self.volume = 0
        self.freq = 0
        self.period = 2048
        self.timer = 2048
        self.pos = 0
        self.ram = bytearray(16)


class _Noise:
    def __init__(self):
        self.enabled = False
        self.dac = False
        self.length = 0
        self.length_en = False
        self.volume = 0
        self.env_vol = 0
        self.env_add = False
        self.env_period = 0
        self.env_timer = 0
        self.clock_shift = 0
        self.width7 = False
        self.divisor = 0
        self.period = 8
        self.timer = 8
        self.lfsr = 0x7FFF


class APU:
    def __init__(self, gb):
        self.gb = gb
        self.master = True
        self.nr50 = 0x77
        self.nr51 = 0xF3
        self.ch1 = _Pulse()
        self.ch2 = _Pulse()
        self.ch3 = _Wave()
        self.ch4 = _Noise()
        self.seq_acc = 0
        self.seq_step = 0
        self.sample_acc = 0
        self.samples = array.array("h")
        self.reset()

    def reset(self) -> None:
        self.master = True
        self.nr50 = 0x77
        self.nr51 = 0xF3
        self.ch1 = _Pulse()
        self.ch2 = _Pulse()
        self.ch3 = _Wave()
        self.ch4 = _Noise()
        self.seq_acc = 0
        self.seq_step = 0
        self.sample_acc = 0
        self.samples = array.array("h")

    def read(self, addr: int) -> int:
        if 0xFF30 <= addr <= 0xFF3F:
            return self.ch3.ram[addr - 0xFF30]
        if addr == 0xFF26:
            if not self.master:
                return 0x70
            status = 0
            if self.ch1.enabled:
                status |= 1
            if self.ch2.enabled:
                status |= 2
            if self.ch3.enabled:
                status |= 4
            if self.ch4.enabled:
                status |= 8
            return 0xF0 | status
        if addr == 0xFF10:
            return 0x80 | (self.ch1.sweep_period << 4) | (0x08 if self.ch1.sweep_neg else 0) | self.ch1.sweep_shift
        if addr == 0xFF11:
            return (self.ch1.duty << 6) | 0x3F
        if addr == 0xFF12:
            return _env_byte(self.ch1)
        if addr == 0xFF14:
            return 0xBF | (0x40 if self.ch1.length_en else 0)
        if addr == 0xFF16:
            return (self.ch2.duty << 6) | 0x3F
        if addr == 0xFF17:
            return _env_byte(self.ch2)
        if addr == 0xFF19:
            return 0xBF | (0x40 if self.ch2.length_en else 0)
        if addr == 0xFF1A:
            return 0x7F | (0x80 if self.ch3.dac else 0)
        if addr == 0xFF1C:
            return 0x9F | (self.ch3.volume << 5)
        if addr == 0xFF1E:
            return 0xBF | (0x40 if self.ch3.length_en else 0)
        if addr == 0xFF21:
            return _env_byte(self.ch4)
        if addr == 0xFF22:
            return (
                (self.ch4.clock_shift << 4)
                | (0x08 if self.ch4.width7 else 0)
                | self.ch4.divisor
            )
        if addr == 0xFF23:
            return 0xBF | (0x40 if self.ch4.length_en else 0)
        if addr == 0xFF24:
            return self.nr50
        if addr == 0xFF25:
            return self.nr51
        return 0xFF

    def write(self, addr: int, value: int) -> None:
        if addr == 0xFF26:
            on = bool(value & 0x80)
            if self.master and not on:
                self.master = False
                self.ch1.enabled = self.ch2.enabled = False
                self.ch3.enabled = self.ch4.enabled = False
            else:
                self.master = on
            return
        if not self.master:
            return
        if 0xFF30 <= addr <= 0xFF3F:
            self.ch3.ram[addr - 0xFF30] = value
            return
        if addr == 0xFF10:
            self.ch1.sweep_period = (value >> 4) & 7
            self.ch1.sweep_neg = bool(value & 0x08)
            self.ch1.sweep_shift = value & 7
        elif addr == 0xFF11:
            self.ch1.duty = value >> 6
            self.ch1.length = 64 - (value & 0x3F)
        elif addr == 0xFF12:
            _write_env(self.ch1, value)
        elif addr == 0xFF13:
            self.ch1.freq = (self.ch1.freq & 0x700) | value
            _retune(self.ch1, 4)
        elif addr == 0xFF14:
            self.ch1.freq = (self.ch1.freq & 0xFF) | ((value & 7) << 8)
            self.ch1.length_en = bool(value & 0x40)
            _retune(self.ch1, 4)
            if value & 0x80:
                _trigger_pulse(self.ch1, sweep=True)
        elif addr == 0xFF16:
            self.ch2.duty = value >> 6
            self.ch2.length = 64 - (value & 0x3F)
        elif addr == 0xFF17:
            _write_env(self.ch2, value)
        elif addr == 0xFF18:
            self.ch2.freq = (self.ch2.freq & 0x700) | value
            _retune(self.ch2, 4)
        elif addr == 0xFF19:
            self.ch2.freq = (self.ch2.freq & 0xFF) | ((value & 7) << 8)
            self.ch2.length_en = bool(value & 0x40)
            _retune(self.ch2, 4)
            if value & 0x80:
                _trigger_pulse(self.ch2, sweep=False)
        elif addr == 0xFF1A:
            self.ch3.dac = bool(value & 0x80)
            if not self.ch3.dac:
                self.ch3.enabled = False
        elif addr == 0xFF1B:
            self.ch3.length = 256 - value
        elif addr == 0xFF1C:
            self.ch3.volume = (value >> 5) & 3
        elif addr == 0xFF1D:
            self.ch3.freq = (self.ch3.freq & 0x700) | value
            _retune(self.ch3, 2)
        elif addr == 0xFF1E:
            self.ch3.freq = (self.ch3.freq & 0xFF) | ((value & 7) << 8)
            self.ch3.length_en = bool(value & 0x40)
            _retune(self.ch3, 2)
            if value & 0x80:
                self.ch3.enabled = self.ch3.dac
                if self.ch3.length == 0:
                    self.ch3.length = 256
                self.ch3.timer = self.ch3.period
                self.ch3.pos = 0
        elif addr == 0xFF20:
            self.ch4.length = 64 - (value & 0x3F)
        elif addr == 0xFF21:
            _write_env(self.ch4, value)
        elif addr == 0xFF22:
            self.ch4.clock_shift = value >> 4
            self.ch4.width7 = bool(value & 0x08)
            self.ch4.divisor = value & 7
            _retune_noise(self.ch4)
        elif addr == 0xFF23:
            self.ch4.length_en = bool(value & 0x40)
            if value & 0x80:
                self.ch4.enabled = self.ch4.dac
                if self.ch4.length == 0:
                    self.ch4.length = 64
                self.ch4.volume = self.ch4.env_vol
                self.ch4.env_timer = self.ch4.env_period
                self.ch4.lfsr = 0x7FFF
                _retune_noise(self.ch4)
                self.ch4.timer = self.ch4.period
        elif addr == 0xFF24:
            self.nr50 = value
        elif addr == 0xFF25:
            self.nr51 = value

    def tick(self, dots: int) -> None:
        if dots <= 0:
            return
        self.seq_acc += dots
        while self.seq_acc >= 8192:
            self.seq_acc -= 8192
            step = self.seq_step
            if step in (0, 2, 4, 6):
                _length(self.ch1)
                _length(self.ch2)
                _length(self.ch3)
                _length(self.ch4)
            if step in (2, 6):
                _sweep(self.ch1)
            if step == 7:
                _envelope(self.ch1)
                _envelope(self.ch2)
                _envelope(self.ch4)
            self.seq_step = (step + 1) & 7
        _clock(self.ch1, dots)
        _clock(self.ch2, dots)
        _clock(self.ch3, dots)
        _clock_noise(self.ch4, dots)
        self.sample_acc += dots * 44100
        while self.sample_acc >= 4194304:
            self.sample_acc -= 4194304
            self._emit()

    def take_samples(self) -> bytes:
        data = self.samples.tobytes()
        self.samples = array.array("h")
        return data

    def _emit(self) -> None:
        if not self.master:
            self.samples.append(0)
            self.samples.append(0)
            return
        amps = (
            _pulse_amp(self.ch1),
            _pulse_amp(self.ch2),
            _wave_amp(self.ch3),
            _noise_amp(self.ch4),
        )
        left = right = 0
        sel = self.nr51
        for i, amp in enumerate(amps):
            if sel & (1 << i):
                right += amp
            if sel & (1 << (i + 4)):
                left += amp
        lv = (self.nr50 >> 4) & 7
        rv = self.nr50 & 7
        self.samples.append(_scale(left, lv))
        self.samples.append(_scale(right, rv))


def _env_byte(ch) -> int:
    return (ch.env_vol << 4) | (0x08 if ch.env_add else 0) | ch.env_period


def _write_env(ch, value: int) -> None:
    ch.env_vol = value >> 4
    ch.env_add = bool(value & 0x08)
    ch.env_period = value & 7
    ch.dac = bool(value & 0xF8)
    if not ch.dac:
        ch.enabled = False


def _retune(ch, scale: int) -> None:
    ch.period = max(scale, (2048 - (ch.freq & 0x7FF)) * scale)


def _retune_noise(ch) -> None:
    ch.period = max(4, _NOISE_DIV[ch.divisor] << ch.clock_shift)


def _trigger_pulse(ch, sweep: bool) -> None:
    ch.enabled = ch.dac
    if ch.length == 0:
        ch.length = 64
    ch.timer = ch.period
    ch.volume = ch.env_vol
    ch.env_timer = ch.env_period
    if sweep:
        ch.shadow = ch.freq & 0x7FF
        ch.sweep_timer = ch.sweep_period or 8
        ch.sweep_en = ch.sweep_period > 0 or ch.sweep_shift > 0
        if ch.sweep_shift:
            _sweep_calc(ch)


def _clock(ch, dots: int) -> None:
    if not ch.enabled or ch.period <= 0:
        return
    ch.timer -= dots
    if ch.timer > 0:
        return
    steps = 1 + (-ch.timer) // ch.period
    ch.timer += steps * ch.period
    if isinstance(ch, _Wave):
        ch.pos = (ch.pos + steps) & 31
    else:
        ch.duty_pos = (ch.duty_pos + steps) & 7


def _clock_noise(ch, dots: int) -> None:
    if not ch.enabled or ch.period <= 0:
        return
    ch.timer -= dots
    if ch.timer > 0:
        return
    steps = 1 + (-ch.timer) // ch.period
    ch.timer += steps * ch.period
    for _ in range(steps):
        bit = (ch.lfsr ^ (ch.lfsr >> 1)) & 1
        ch.lfsr = (ch.lfsr >> 1) | (bit << 14)
        if ch.width7:
            ch.lfsr = (ch.lfsr & ~(1 << 6)) | (bit << 6)


def _length(ch) -> None:
    if ch.length_en and ch.length > 0:
        ch.length -= 1
        if ch.length == 0:
            ch.enabled = False


def _envelope(ch) -> None:
    if not ch.enabled or ch.env_period == 0:
        return
    if ch.env_timer > 0:
        ch.env_timer -= 1
    if ch.env_timer <= 0:
        ch.env_timer = ch.env_period
        if ch.env_add:
            if ch.volume < 15:
                ch.volume += 1
        elif ch.volume > 0:
            ch.volume -= 1


def _sweep_calc(ch) -> int | None:
    shifted = ch.shadow >> ch.sweep_shift
    updated = ch.shadow - shifted if ch.sweep_neg else ch.shadow + shifted
    if updated > 2047:
        ch.enabled = False
        return None
    return updated


def _sweep(ch) -> None:
    if not ch.sweep_en:
        return
    if ch.sweep_timer > 0:
        ch.sweep_timer -= 1
    if ch.sweep_timer > 0:
        return
    ch.sweep_timer = ch.sweep_period or 8
    if ch.sweep_period == 0:
        return
    updated = _sweep_calc(ch)
    if updated is not None and ch.sweep_shift > 0:
        ch.shadow = updated
        ch.freq = updated
        _retune(ch, 4)
        _sweep_calc(ch)


def _pulse_amp(ch) -> int:
    if not ch.enabled or not ch.dac:
        return 0
    if _DUTY[ch.duty][ch.duty_pos]:
        return ch.volume
    return 0


def _wave_amp(ch) -> int:
    if not ch.enabled or not ch.dac or ch.volume == 0:
        return 0
    byte = ch.ram[ch.pos >> 1]
    sample = byte & 0x0F if ch.pos & 1 else byte >> 4
    return sample >> (ch.volume - 1)


def _noise_amp(ch) -> int:
    if not ch.enabled or not ch.dac:
        return 0
    if ch.lfsr & 1:
        return 0
    return ch.volume


def _scale(total: int, vol: int) -> int:
    sample = total * vol * 70
    if sample > 32767:
        return 32767
    return sample
