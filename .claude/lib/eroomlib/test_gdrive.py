#!/usr/bin/env python3
"""gdrive(셀러라이프 드라이브 헬퍼) 회귀 테스트 — subprocess 를 가짜로 갈아끼워 네트워크 없이 돈다.

    python .claude/lib/eroomlib/test_gdrive.py

지키려는 계약:
  1. **로컬 우선** — 로컬 runs 에 통다운이 있으면 드라이브를 아예 부르지 않는다.
  2. **md5 캐시** — 캐시 파일의 md5 가 드라이브와 같으면 재다운로드하지 않는다.
  3. **검증 실패는 예외** — 다운로드/업로드 후 md5 불일치는 조용히 넘어가지 않는다.
  4. 레이아웃 2종(<date>/raw/ 와 <date>/ 평면)을 모두 흡수한다.
  5. **원본만 미러** — 날짜 폴더에 가공 산출물이 같이 있어도 raw/ 만 내려받는다.
  6. **7일 규칙** — 날짜를 안 주면 최신을 고르고, 낡았거나 zip 이 없으면 새로 받는다.
     날짜를 명시하면 낡아도 그 날짜를 그대로 쓴다(재현성).
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eroomlib import gdrive  # noqa: E402


class FakeProc:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


class GdriveTestBase(unittest.TestCase):
    """cfg 와 subprocess.run 을 가짜로 바꾼 공통 베이스."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gdrive_test_")
        self.runs = os.path.join(self.tmp, "runs")
        self.cache = os.path.join(self.tmp, "cache")
        os.makedirs(self.runs, exist_ok=True)

        self._orig_cfg = gdrive.cfg
        cfg_map = {"paths.sellerlife_runs": self.runs,
                   "paths.sellerlife_cache": self.cache,
                   "drive.sellerlife_folder": "ROOT"}
        gdrive.cfg = lambda k, default=None, required=False: cfg_map.get(k, default)

        # 가짜 드라이브: {folder_id: [file dict, ...]}, {file_id: bytes}
        self.remote_tree = {}
        self.remote_bytes = {}
        self.calls = []
        self._orig_run = gdrive.subprocess.run
        gdrive.subprocess.run = self._fake_run

    def tearDown(self):
        gdrive.cfg = self._orig_cfg
        gdrive.subprocess.run = self._orig_run
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_run(self, cmd, cwd=None, **kw):
        self.calls.append(cmd)
        args = [str(c) for c in cmd]
        if "list" in args:
            q = json.loads(args[args.index("--params") + 1])["q"]
            fid = q.split("'")[1]
            return FakeProc(json.dumps({"files": self.remote_tree.get(fid, [])}))
        if "get" in args:  # alt=media 다운로드 — cwd 에 -o 파일명으로 쓴다
            params = json.loads(args[args.index("--params") + 1])
            name = args[args.index("-o") + 1]
            with open(os.path.join(cwd, name), "wb") as f:
                f.write(self.remote_bytes.get(params["fileId"], b""))
            return FakeProc("")
        if "update" in args or "create" in args:
            up_i = args.index("--upload") if "--upload" in args else -1
            md5 = ""
            if up_i >= 0:
                with open(os.path.join(cwd, args[up_i + 1]), "rb") as f:
                    md5 = hashlib.md5(f.read()).hexdigest()
            return FakeProc(json.dumps({"id": "NEW", "name": "x",
                                        "md5Checksum": md5}))
        return FakeProc("{}")

    # -- 헬퍼 ---------------------------------------------------------------
    def put_local(self, *parts, content=b"data"):
        p = os.path.join(*parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(content)
        return p

    def put_remote(self, folder_id, name, content=b"data", mime="application/x"):
        fid = f"id_{folder_id}_{name}"
        entry = {"id": fid, "name": name, "mimeType": mime,
                 "size": str(len(content)),
                 "md5Checksum": hashlib.md5(content).hexdigest()}
        self.remote_tree.setdefault(folder_id, []).append(entry)
        self.remote_bytes[fid] = content
        return entry

    def put_remote_folder(self, parent_id, name):
        fid = f"fold_{parent_id}_{name}"
        self.remote_tree.setdefault(parent_id, []).append(
            {"id": fid, "name": name, "mimeType": gdrive.FOLDER_MIME})
        return fid


def ymd(days_ago):
    """오늘로부터 days_ago 일 전 날짜의 통다운 폴더명."""
    return (date.today() - timedelta(days=days_ago)).strftime("%y%m%d")


class ResolveRawDirTest(GdriveTestBase):
    # 날짜를 명시하는 경로는 zip 유무를 따지지 않는다(경고만) — 기존 계약 유지
    def resolve(self, d):
        return gdrive.resolve_raw_dir(d)

    def test_로컬_raw_레이아웃이_있으면_드라이브를_부르지_않는다(self):
        self.put_local(self.runs, "260731", "raw", "a.xlsx")
        got = self.resolve("260731")
        self.assertEqual(got, os.path.join(self.runs, "260731", "raw"))
        self.assertEqual(self.calls, [])

    def test_로컬_평면_레이아웃도_흡수한다(self):
        self.put_local(self.runs, "260712", "b.zip")
        got = self.resolve("260712")
        self.assertEqual(got, os.path.join(self.runs, "260712"))
        self.assertEqual(self.calls, [])

    def test_빈_로컬_폴더는_무시하고_드라이브로_간다(self):
        os.makedirs(os.path.join(self.runs, "260731", "raw"))
        date_fold = self.put_remote_folder("ROOT", "260731")
        raw_fold = self.put_remote_folder(date_fold, "raw")
        self.put_remote(raw_fold, "a.xlsx", b"xlsx-bytes")
        got = self.resolve("260731")
        self.assertEqual(got, os.path.join(self.cache, "runs", "260731", "raw"))
        with open(os.path.join(got, "a.xlsx"), "rb") as f:
            self.assertEqual(f.read(), b"xlsx-bytes")

    def test_드라이브_평면_레이아웃(self):
        date_fold = self.put_remote_folder("ROOT", "260712")
        self.put_remote(date_fold, "a.xlsx", b"x")
        got = self.resolve("260712")
        self.assertEqual(got, os.path.join(self.cache, "runs", "260712"))

    def test_드라이브에도_없으면_예외(self):
        with self.assertRaises(RuntimeError):
            self.resolve("999999")

    def test_날짜를_명시하면_낡아도_그날짜를_쓴다(self):
        """재현성 — 지정한 날짜를 말없이 최신으로 갈아치우지 않는다."""
        old = ymd(90)
        self.put_local(self.runs, old, "raw", "a.zip")
        self.put_remote_folder("ROOT", ymd(0))          # 최신이 따로 있어도
        got = self.resolve(old)
        self.assertEqual(got, os.path.join(self.runs, old, "raw"))


class EnsureRunOnlyRawTest(GdriveTestBase):
    def test_가공산출물은_안_내려받는다(self):
        """날짜 폴더에 filtered/·최종_*.xlsx 가 같이 있어도 raw/ 만 미러한다."""
        date_fold = self.put_remote_folder("ROOT", "260731")
        raw_fold = self.put_remote_folder(date_fold, "raw")
        self.put_remote(raw_fold, "big.zip", b"zip-bytes")
        filt = self.put_remote_folder(date_fold, "filtered")
        self.put_remote(filt, "buk.xlsx", b"heavy")
        self.put_remote(date_fold, "최종_통합.xlsx", b"final")

        base = gdrive.ensure_run("260731")
        self.assertTrue(os.path.exists(os.path.join(base, "raw", "big.zip")))
        self.assertFalse(os.path.exists(os.path.join(base, "filtered")))
        self.assertFalse(os.path.exists(os.path.join(base, "최종_통합.xlsx")))

    def test_only_raw_False_면_통째로_받는다(self):
        date_fold = self.put_remote_folder("ROOT", "260731")
        raw_fold = self.put_remote_folder(date_fold, "raw")
        self.put_remote(raw_fold, "big.zip", b"z")
        self.put_remote(date_fold, "최종_통합.xlsx", b"final")
        base = gdrive.ensure_run("260731", only_raw=False)
        self.assertTrue(os.path.exists(os.path.join(base, "최종_통합.xlsx")))


class FreshnessTest(GdriveTestBase):
    """7일 규칙: 날짜를 안 주면 최신 + 신선도 판정."""

    def setUp(self):
        super().setUp()
        self.refreshed = []
        self._orig_refresh = gdrive.refresh_run

        def fake_refresh(**kw):
            new = ymd(0)
            self.refreshed.append(new)
            self.put_local(self.runs, new, "raw", "새통다운.zip")
            return new

        gdrive.refresh_run = fake_refresh

    def tearDown(self):
        gdrive.refresh_run = self._orig_refresh
        super().tearDown()

    def test_날짜파싱(self):
        self.assertEqual(gdrive.parse_run_date("260803"), date(2026, 8, 3))
        self.assertIsNone(gdrive.parse_run_date("_legacy"))
        self.assertIsNone(gdrive.parse_run_date("keyword_blacklist"))
        self.assertIsNone(gdrive.parse_run_date("269999"))

    def test_통다운_폴더만_목록에_잡힌다(self):
        self.put_remote_folder("ROOT", "260712")
        self.put_remote_folder("ROOT", "260803")
        self.put_remote_folder("ROOT", "_legacy")
        self.put_remote_folder("ROOT", "keyword_blacklist")
        self.assertEqual(gdrive.list_run_dates(), ["260712", "260803"])
        self.assertEqual(gdrive.latest_run_date(), "260803")

    def test_7일_이내면_최신을_그대로_쓴다(self):
        recent = ymd(3)
        self.put_remote_folder("ROOT", recent)
        self.put_local(self.runs, recent, "raw", "a.zip")
        got = gdrive.resolve_raw_dir()
        self.assertEqual(got, os.path.join(self.runs, recent, "raw"))
        self.assertEqual(self.refreshed, [])

    def test_7일_초과면_새로_받는다(self):
        stale = ymd(8)
        self.put_remote_folder("ROOT", stale)
        self.put_local(self.runs, stale, "raw", "a.zip")
        got = gdrive.resolve_raw_dir()
        self.assertEqual(self.refreshed, [ymd(0)])
        self.assertEqual(got, os.path.join(self.runs, ymd(0), "raw"))

    def test_경계_정확히_7일은_안_받는다(self):
        edge = ymd(7)
        self.put_remote_folder("ROOT", edge)
        self.put_local(self.runs, edge, "raw", "a.zip")
        gdrive.resolve_raw_dir()
        self.assertEqual(self.refreshed, [])

    def test_zip이_없으면_신선해도_새로_받는다(self):
        """추출본 3개만 있는 폴더 = 3개 대분류 밖 상품이 조용히 누락되는 상태."""
        recent = ymd(1)
        self.put_remote_folder("ROOT", recent)
        self.put_local(self.runs, recent, "raw", "SellarSourcing_디지털&가전.xlsx")
        gdrive.resolve_raw_dir()
        self.assertEqual(self.refreshed, [ymd(0)])

    def test_통다운이_하나도_없으면_받는다(self):
        gdrive.resolve_raw_dir()
        self.assertEqual(self.refreshed, [ymd(0)])

    def test_자동갱신_끄면_낡아도_안_받는다(self):
        stale = ymd(30)
        self.put_remote_folder("ROOT", stale)
        self.put_local(self.runs, stale, "raw", "a.zip")
        got = gdrive.resolve_raw_dir(allow_refresh=False)
        self.assertEqual(self.refreshed, [])
        self.assertEqual(got, os.path.join(self.runs, stale, "raw"))

    def test_명시한_날짜는_zip이_없어도_안_받는다(self):
        old = ymd(60)
        self.put_local(self.runs, old, "raw", "SellarSourcing_디지털&가전.xlsx")
        got = gdrive.resolve_raw_dir(old)
        self.assertEqual(self.refreshed, [])
        self.assertEqual(got, os.path.join(self.runs, old, "raw"))


class MirrorTest(GdriveTestBase):
    def test_md5_같은_캐시는_재다운로드하지_않는다(self):
        date_fold = self.put_remote_folder("ROOT", "260731")
        self.put_remote(date_fold, "a.xlsx", b"same")
        dest = os.path.join(self.cache, "runs", "260731")
        self.put_local(dest, "a.xlsx", content=b"same")
        gdrive.ensure_run("260731")
        gets = [c for c in self.calls if "get" in [str(x) for x in c]]
        self.assertEqual(gets, [])

    def test_md5_다른_캐시는_다시_받는다(self):
        date_fold = self.put_remote_folder("ROOT", "260731")
        self.put_remote(date_fold, "a.xlsx", b"new-bytes")
        dest = os.path.join(self.cache, "runs", "260731")
        self.put_local(dest, "a.xlsx", content=b"stale")
        gdrive.ensure_run("260731")
        with open(os.path.join(dest, "a.xlsx"), "rb") as f:
            self.assertEqual(f.read(), b"new-bytes")


class BlacklistTest(GdriveTestBase):
    def _seed_remote_blacklist(self, content=b"bl"):
        d = self.put_remote_folder("ROOT", gdrive.BLACKLIST_DIRNAME)
        return self.put_remote(d, gdrive.BLACKLIST_FILENAME, content)

    def test_캐시_md5_일치면_재사용(self):
        self._seed_remote_blacklist(b"bl")
        self.put_local(gdrive.blacklist_cache_path(), content=b"bl")
        p = gdrive.ensure_blacklist()
        self.assertEqual(p, gdrive.blacklist_cache_path())
        gets = [c for c in self.calls if "get" in [str(x) for x in c]]
        self.assertEqual(gets, [])

    def test_캐시_없으면_다운로드(self):
        self._seed_remote_blacklist(b"master")
        p = gdrive.ensure_blacklist()
        with open(p, "rb") as f:
            self.assertEqual(f.read(), b"master")

    def test_push_후_md5_불일치는_예외(self):
        self._seed_remote_blacklist()
        p = self.put_local(gdrive.blacklist_cache_path(), content=b"local")

        orig = self._fake_run

        def corrupt_run(cmd, cwd=None, **kw):
            args = [str(c) for c in cmd]
            if "update" in args:
                return FakeProc(json.dumps({"id": "X", "md5Checksum": "broken"}))
            return orig(cmd, cwd=cwd, **kw)

        gdrive.subprocess.run = corrupt_run
        with self.assertRaises(RuntimeError):
            gdrive.push_blacklist(p)


class UploadRunTest(GdriveTestBase):
    def test_동일_md5는_건너뛰고_새_파일만_올린다(self):
        base = os.path.join(self.tmp, "run260801")
        self.put_local(base, "최종.xlsx", content=b"fin")
        self.put_local(base, "raw", "big.xlsx", content=b"raw")
        self.put_local(base, "raw", "~$big.xlsx", content=b"lock")  # 엑셀 잠금 — 제외
        # 드라이브에 이미 같은 내용의 최종.xlsx 가 있다
        fold = self.put_remote_folder("ROOT", "260801")
        self.put_remote(fold, "최종.xlsx", b"fin")
        stats = gdrive.upload_run(base, name="260801")
        self.assertEqual(stats["skip"], 1)
        self.assertEqual(stats["create"], 1)   # raw/big.xlsx 만 신규
        self.assertEqual(stats["update"], 0)

    def test_omit은_아예_올리지_않는다(self):
        """zip 이 원본이라 추출본(SellarSourcing_*.xlsx)은 드라이브에 안 쌓는다."""
        base = os.path.join(self.tmp, "run260806")
        self.put_local(base, "raw", "260806_sellerlife_전체카테고리.zip", content=b"zip")
        self.put_local(base, "raw", "SellarSourcing_디지털&가전.xlsx", content=b"huge")
        self.put_local(base, "최종_통합.xlsx", content=b"fin")

        def omit(rel):
            parts = rel.replace("\\", "/").split("/")
            return (len(parts) == 2 and parts[0] == "raw"
                    and parts[1].startswith("SellarSourcing_"))

        stats = gdrive.upload_run(base, name="260806", omit=omit)
        self.assertEqual(stats["omit"], 1)
        self.assertEqual(stats["create"], 2)   # zip + 최종_통합
        uploaded = [str(c[c.index("--upload") + 1]) for c in self.calls if "--upload" in c]
        self.assertNotIn("SellarSourcing_디지털&가전.xlsx", uploaded)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    unittest.main(verbosity=2)
