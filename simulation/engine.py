"""Mesin Discrete-Event Simulation (DES) murni untuk antrian bengkel.

Tanpa SimPy: hanya list, dict, library standar Python, dan NumPy (untuk statistik).
Modul ini di-import oleh Colab (saat joblib.dump) dan Flask (saat joblib.load),
sehingga path modul `simulation.engine` harus sama di kedua tempat.

Komponen : 1 resepsionis/kasir, 2 montir (paralel).
Alur mobil: ARRIVAL -> REGISTRATION -> SERVICE_CHECK -> SERVICE_START
            -> SERVICE_END -> PAYMENT -> DEPARTURE
Aturan resepsionis: bila bebas dan ada dua antrian terisi, kasir (pembayaran)
didahulukan agar mobil yang selesai cepat keluar.
"""
import random
from copy import deepcopy

import numpy as np

DISCIPLINES = ("FIFO", "LIFO", "RANDOM")

DEFAULTS = {
    "mode": "random",
    "discipline": "FIFO",
    "n_cars": 20,
    "mean_interarrival": 8.0,
    "reg_mean": 2.0,
    "reg_std": 0.5,
    "service_mean": 12.0,
    "service_std": 3.0,
    "pay_mean": 2.0,
    "pay_std": 0.5,
    "seed": 42,
}

# Urutan prioritas jika beberapa event terjadi pada Clock yang sama
PRIORITY = {"PAY_END": 0, "SERVICE_END": 1, "REG_END": 2, "ARRIVAL": 3}


def parse_numbers(value, name="data"):
    """Ubah '0, 3, 5' atau [0, 3, 5] menjadi list float."""
    if value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, str):
        value = value.replace("[", " ").replace("]", " ").replace(";", ",").replace("\n", ",")
        parts = [x.strip() for x in value.split(",") if x.strip()]
    else:
        parts = list(value)
    try:
        return [float(x) for x in parts]
    except (TypeError, ValueError):
        raise ValueError(f"{name}: semua nilai harus berupa angka, dipisahkan koma.")


class BengkelDESEngine:
    """Engine DES bengkel. Objek ini yang diekspor ke file .joblib."""

    def __init__(self, defaults=None):
        self.defaults = deepcopy(DEFAULTS)
        if defaults:
            self.defaults.update(defaults)

    def get_defaults(self):
        return deepcopy(self.defaults)

    # ------------------------------------------------------------------ data
    def _build_data(self, p, rng):
        mode = str(p.get("mode", "random")).lower()
        if mode == "manual":
            arr = parse_numbers(p.get("arrivals"), "Waktu kedatangan")
            srv = parse_numbers(p.get("service"), "Waktu perbaikan")
            reg = parse_numbers(p.get("reg"), "Waktu pendaftaran")
            pay = parse_numbers(p.get("pay"), "Waktu pembayaran")
            n = len(arr)
            if n == 0:
                raise ValueError("Waktu kedatangan tidak boleh kosong.")
            if any(arr[i] > arr[i + 1] for i in range(n - 1)):
                raise ValueError("Waktu kedatangan harus berurutan naik.")
            reg = reg or [float(p["reg_mean"])]
            pay = pay or [float(p["pay_mean"])]
            if not srv:
                raise ValueError("Waktu perbaikan tidak boleh kosong.")

            def fit(lst, label):
                if len(lst) == 1:
                    return lst * n
                if len(lst) != n:
                    raise ValueError(f"{label}: butuh {n} nilai (atau 1 nilai untuk semua mobil), terisi {len(lst)}.")
                return lst

            reg, srv, pay = fit(reg, "Waktu pendaftaran"), fit(srv, "Waktu perbaikan"), fit(pay, "Waktu pembayaran")
            if min(arr) < 0 or min(reg + srv + pay) <= 0:
                raise ValueError("Waktu kedatangan tidak boleh negatif dan durasi layanan harus > 0.")
            return arr, reg, srv, pay

        n = int(p["n_cars"])
        if not 1 <= n <= 500:
            raise ValueError("Jumlah mobil harus 1 sampai 500.")
        if float(p["mean_interarrival"]) <= 0:
            raise ValueError("Rata-rata antar-kedatangan harus > 0.")

        def normal(m, s):
            return max(0.5, round(rng.gauss(float(m), float(s)), 2))

        arr, t = [], 0.0
        for i in range(n):
            if i > 0:
                t += rng.expovariate(1.0 / float(p["mean_interarrival"]))
            arr.append(round(t, 2))
        reg = [normal(p["reg_mean"], p["reg_std"]) for _ in range(n)]
        srv = [normal(p["service_mean"], p["service_std"]) for _ in range(n)]
        pay = [normal(p["pay_mean"], p["pay_std"]) for _ in range(n)]
        return arr, reg, srv, pay

    # ------------------------------------------------------------------- run
    def run(self, params=None):
        p = self.get_defaults()
        p.update(params or {})
        disc = str(p.get("discipline", "FIFO")).upper()
        if disc not in DISCIPLINES:
            raise ValueError("Disiplin antrian harus FIFO, LIFO, atau RANDOM.")
        p["discipline"] = disc
        rng = random.Random(int(p.get("seed") or 0))
        arr, reg, srv, pay = self._build_data(p, rng)
        return self._simulate(p, disc, rng, arr, reg, srv, pay)

    def _simulate(self, p, disc, rng, arr, reg, srv, pay):
        n = len(arr)
        cars = {i + 1: {"arrival": arr[i], "reg": reg[i], "srv": srv[i], "pay": pay[i],
                        "reg_wait": 0.0, "svc_wait": 0.0, "pay_wait": 0.0, "depart": None}
                for i in range(n)}
        events, seq = [], 0                    # Future Event List (list biasa)
        reg_q, wait_q, pay_q = [], [], []      # isi: (id_mobil, waktu_masuk_antrian)
        mech = [None, None]                    # id mobil atau None
        busy = [0.0, 0.0]
        recep = {"car": None, "kind": None}
        recep_busy = 0.0
        done = 0
        rows, series = [], []

        def push(t, typ, cid):
            nonlocal seq
            events.append((round(t, 4), PRIORITY[typ], seq, typ, cid))
            seq += 1

        def pick(q):
            if disc == "FIFO":
                return q.pop(0)
            if disc == "LIFO":
                return q.pop(-1)
            return q.pop(rng.randrange(len(q)))      # RANDOM / SIRO

        def ids(q):
            return [f"C{c}" for c, _ in q]

        def mtxt(i):
            return "IDLE" if mech[i] is None else f"BUSY (C{mech[i]})"

        def rtxt():
            return "IDLE" if recep["car"] is None else f"{recep['kind']} (C{recep['car']})"

        def log(t, typ, cid, detail, wait=None):
            rows.append({"no": len(rows) + 1, "clock": round(t, 2), "event": typ, "car": f"C{cid}",
                         "detail": detail, "reg_queue": ids(reg_q), "wait_queue": ids(wait_q),
                         "pay_queue": ids(pay_q), "m1": mtxt(0), "m2": mtxt(1), "recep": rtxt(),
                         "wait": None if wait is None else round(wait, 2), "done": done})
            series.append({"clock": round(t, 2), "reg": len(reg_q), "wait": len(wait_q), "pay": len(pay_q)})

        def start_recep(t):
            nonlocal recep_busy
            if recep["car"] is not None:
                return
            if pay_q:
                cid, enq = pick(pay_q)
                dur = cars[cid]["pay"]
                cars[cid]["pay_wait"] = t - enq
                recep.update(car=cid, kind="PAY")
                recep_busy += dur
                log(t, "PAYMENT", cid, f"Mulai bayar di kasir (durasi {dur:g})", t - enq)
                push(t + dur, "PAY_END", cid)
            elif reg_q:
                cid, enq = pick(reg_q)
                dur = cars[cid]["reg"]
                cars[cid]["reg_wait"] = t - enq
                recep.update(car=cid, kind="REG")
                recep_busy += dur
                log(t, "REGISTRATION", cid, f"Mulai mendaftar di resepsionis (durasi {dur:g})", t - enq)
                push(t + dur, "REG_END", cid)

        def start_service(t, cid, enq, m):
            mech[m] = cid
            dur = cars[cid]["srv"]
            busy[m] += dur
            cars[cid]["svc_wait"] = t - enq
            log(t, "SERVICE_START", cid, f"Masuk perbaikan di Montir {m + 1} (durasi {dur:g})", t - enq)
            push(t + dur, "SERVICE_END", cid)

        for i in range(n):
            push(arr[i], "ARRIVAL", i + 1)

        clock = 0.0
        while events:
            ev = min(events)
            events.remove(ev)
            clock, _, _, typ, cid = ev
            if typ == "ARRIVAL":
                reg_q.append((cid, clock))
                log(clock, "ARRIVAL", cid, "Mobil tiba, masuk antrian resepsionis")
                start_recep(clock)
            elif typ == "REG_END":
                recep.update(car=None, kind=None)
                idle = [m for m in (0, 1) if mech[m] is None]
                if idle:
                    log(clock, "SERVICE_CHECK", cid, f"Pendaftaran selesai; Montir {idle[0] + 1} IDLE")
                    start_service(clock, cid, clock, idle[0])
                else:
                    wait_q.append((cid, clock))
                    log(clock, "SERVICE_CHECK", cid, "Pendaftaran selesai; kedua montir BUSY, masuk ruang tunggu")
                start_recep(clock)
            elif typ == "SERVICE_END":
                m = mech.index(cid)
                mech[m] = None
                pay_q.append((cid, clock))
                log(clock, "SERVICE_END", cid, f"Perbaikan selesai di Montir {m + 1}, menuju kasir")
                if wait_q:
                    ncid, enq = pick(wait_q)
                    start_service(clock, ncid, enq, m)
                start_recep(clock)
            elif typ == "PAY_END":
                recep.update(car=None, kind=None)
                cars[cid]["depart"] = clock
                done += 1
                log(clock, "DEPARTURE", cid, "Pembayaran selesai, mobil keluar bengkel")
                start_recep(clock)

        total = clock if clock > 0 else 1.0
        sw = np.array([c["svc_wait"] for c in cars.values()])
        rw = np.array([c["reg_wait"] for c in cars.values()])
        pw = np.array([c["pay_wait"] for c in cars.values()])
        tis = np.array([c["depart"] - c["arrival"] for c in cars.values()])
        stats = {
            "total_served": done,
            "avg_wait": round(float(sw.mean()), 2),
            "max_wait": round(float(sw.max()), 2),
            "avg_wait_reg": round(float(rw.mean()), 2),
            "avg_wait_pay": round(float(pw.mean()), 2),
            "avg_time_in_system": round(float(tis.mean()), 2),
            "util_m1": round(busy[0] / total * 100, 2),
            "util_m2": round(busy[1] / total * 100, 2),
            "util_recep": round(recep_busy / total * 100, 2),
            "total_time": round(clock, 2),
            "max_queue": max(s["wait"] for s in series) if series else 0,
        }
        return {"params": p, "log": rows, "series": series, "stats": stats,
                "input": {"arrivals": arr, "reg": reg, "service": srv, "pay": pay}}
