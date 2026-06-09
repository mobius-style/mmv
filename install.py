#!/usr/bin/env python3
"""
install.py — MOBIUS MMV interactive installer

Usage:
    python3 install.py

Interactive setup for the MOBIUS MMV Answer Entitlement Runtime.
Each step confirms before proceeding; optional components can be skipped.

Author : Taiko Toeda / MOBIUS LLC
License: AGPL-3.0-or-later
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

# ── Utilities ────────────────────────────────────────────────────────────────


def _banner():
    print()
    print("=" * 62)
    print("  MOBIUS MMV — Interactive Installer")
    print("  Answer Entitlement Runtime")
    print("=" * 62)
    print()


def _section(n, title):
    print()
    print(f"{'─' * 62}")
    print(f"  Step {n}: {title}")
    print(f"{'─' * 62}")


def _ok(msg):
    print(f"  \033[32m✅ {msg}\033[0m")


def _warn(msg):
    print(f"  \033[33m⚠️  {msg}\033[0m")


def _fail(msg):
    print(f"  \033[31m❌ {msg}\033[0m")


def _info(msg):
    print(f"     {msg}")


def _ask_yn(prompt, default=True):
    suffix = "[Y/n]" if default else "[y/N]"
    ans = input(f"  {prompt} {suffix}: ").strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes")


def _ask_skip(step_name):
    return _ask_yn(f"{step_name}をスキップしますか？", default=False)


def _run(cmd, check=True, capture=False, **kwargs):
    if capture:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, **kwargs
        )
        if check and r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"Command failed: {cmd}")
        return r
    return subprocess.run(cmd, shell=True, check=check, **kwargs)


def _http_ok(url, timeout=3):
    """Return True if URL responds with 2xx."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


# ── Step 1: Python venv + requirements ─────────────────────────────────────


def step1_python():
    _section(1, "Python 環境の構築")

    # ── Python version check ──
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"

    if v < (3, 13):
        _fail(f"Python {ver_str} が検出されました")
        _info("MOBIUS MMV には Python 3.13 以上が必要です。")
        _info("")
        _info("pyenv でのインストール例:")
        _info("  pyenv install 3.13.2")
        _info("  pyenv local 3.13.2")
        _info("")
        _info("または https://www.python.org/downloads/ からインストールしてください。")
        return False

    _ok(f"Python {ver_str}")

    # ── venv check / create ──
    # Look for venv in parent directory (standard layout: mobius_ai/venv313)
    # or in project root
    venv_candidates = [
        ROOT.parent / "venv313",
        ROOT / "venv",
    ]

    in_venv = (
        hasattr(sys, "real_prefix")
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
    )

    if in_venv:
        _ok(f"仮想環境で実行中: {sys.prefix}")
    else:
        # Check existing venvs
        existing = None
        for p in venv_candidates:
            if (p / "bin" / "python").exists():
                existing = p
                break

        if existing:
            _ok(f"既存の仮想環境を検出: {existing}")
            _info(f"次のコマンドで有効化してください:")
            _info(f"  source {existing}/bin/activate")
            _info(f"  python install.py  # 再実行")
            _info("")
            if not _ask_yn("仮想環境なしで続行しますか？", default=False):
                return False
            _warn("仮想環境なしで続行します")
        else:
            _info("仮想環境が見つかりません。作成します。")
            venv_path = ROOT.parent / "venv313"
            _info(f"作成先: {venv_path}")

            if _ask_yn("仮想環境を作成しますか？"):
                try:
                    _run(f"{sys.executable} -m venv {venv_path}")
                    _ok(f"仮想環境を作成しました: {venv_path}")
                    _info("")
                    _info("仮想環境を有効化して再実行してください:")
                    _info(f"  source {venv_path}/bin/activate")
                    _info(f"  python install.py")
                    return False
                except Exception as e:
                    _fail(f"仮想環境の作成に失敗: {e}")
                    return False
            else:
                _warn("仮想環境なしで続行します")

    # ── requirements.txt install ──
    req_file = ROOT / "requirements.txt"
    if not req_file.exists():
        _fail("requirements.txt が見つかりません")
        _info(f"期待されるパス: {req_file}")
        return False

    _info(f"requirements.txt: {req_file}")
    with open(req_file) as f:
        pkgs = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    _info(f"パッケージ数: {len(pkgs)}")

    if _ask_yn("依存パッケージをインストールしますか？"):
        _info("pip install を実行中...")
        print()
        try:
            _run(f"{sys.executable} -m pip install -r {req_file}")
            print()
            _ok("全パッケージのインストール完了")
        except Exception as e:
            print()
            _fail(f"インストールに失敗: {e}")
            _info("対処法:")
            _info("  1. ネットワーク接続を確認")
            _info("  2. pip を更新: python -m pip install --upgrade pip")
            return False
    else:
        _warn("パッケージインストールをスキップしました")

    return True


# ── Step 2: Ollama + model ─────────────────────────────────────────────────


def step2_ollama():
    _section(2, "Ollama + qwen3.5:9b")

    # ── Ollama binary ──
    ollama_path = shutil.which("ollama")
    if ollama_path:
        _ok(f"Ollama インストール済み: {ollama_path}")
    else:
        _fail("Ollama がインストールされていません")
        _info("")
        _info("インストールコマンド:")
        _info("  curl -fsSL https://ollama.com/install.sh | sh")
        _info("")
        _info("公式サイト: https://ollama.com")
        _info("インストール後に再度 python install.py を実行してください。")
        return False

    # ── ollama serve check ──
    models = []
    try:
        with urllib.request.urlopen(
            "http://localhost:11434/api/tags", timeout=3
        ) as r:
            data = json.loads(r.read())
            models = [m["name"] for m in data.get("models", [])]
        _ok(f"Ollama サーバー稼働中 ({len(models)} モデル)")
    except Exception:
        _fail("Ollama サーバーが起動していません")
        _info("")
        _info("起動方法:")
        _info("  ollama serve          # フォアグラウンド")
        _info("  systemctl start ollama  # systemd 経由")
        _info("")
        _info("サーバーを起動後に再実行してください。")
        return False

    # ── qwen3.5:9b ──
    has_model = any("qwen3.5:9b" in m for m in models)
    if has_model:
        _ok("qwen3.5:9b ダウンロード済み")
        return True

    _warn("qwen3.5:9b が見つかりません")
    _info("MOBIUS MMV のプロダクションモデルです (約6.6GB)")

    if _ask_yn("qwen3.5:9b をダウンロードしますか？"):
        _info("ダウンロード中... (約6.6GB)")
        print()
        try:
            _run("ollama pull qwen3.5:9b")
            print()
            _ok("qwen3.5:9b ダウンロード完了")
        except Exception as e:
            print()
            _fail(f"ダウンロード失敗: {e}")
            _info("手動で実行: ollama pull qwen3.5:9b")
            return False
    else:
        _warn("スキップしました")
        _info("後で手動で実行: ollama pull qwen3.5:9b")

    return True


# ── Step 3: Kiwix ──────────────────────────────────────────────────────────


def _find_zim_files():
    """Search for ZIM files in likely locations. Return list of Paths."""
    search_dirs = [
        ROOT / "kiwix",
        ROOT.parent / "kiwix",
        Path.home() / "kiwix",
    ]
    found = []
    seen = set()
    for d in search_dirs:
        if d.is_dir():
            for f in d.glob("*.zim"):
                real = f.resolve()
                if real not in seen:
                    seen.add(real)
                    found.append(real)
    return found


def _detect_kiwix_serve_path():
    """Return kiwix-serve binary path or None."""
    path = shutil.which("kiwix-serve")
    if path:
        return path
    # Common install locations
    for candidate in ["/usr/bin/kiwix-serve", "/usr/local/bin/kiwix-serve"]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def step3_kiwix():
    _section(3, "Kiwix ローカル Wikipedia（推奨）")

    _info("Kiwix はローカル Wikipedia 検索を提供します。")
    _info("verify ルートの Stage 1b として使用され、")
    _info("Web API なしでも非鮮度クエリに回答可能になります。")
    print()

    if _ask_skip("Kiwix 設定"):
        _warn("スキップしました（推奨だが任意）")
        return True

    # ── kiwix-serve binary ──
    kiwix_bin = _detect_kiwix_serve_path()
    if kiwix_bin:
        _ok(f"kiwix-serve インストール済み: {kiwix_bin}")
    else:
        _warn("kiwix-serve がインストールされていません")
        _info("")
        _info("インストール:")
        _info("  sudo apt install kiwix-tools    # Ubuntu/Debian")
        _info("")
        if not _ask_yn("kiwix-serve なしで続行しますか？"):
            return True
        _warn("kiwix-serve なしで続行します")

    # ── ZIM file search ──
    zim_files = _find_zim_files()
    zim_path = None

    if zim_files:
        _ok(f"ZIM ファイルを検出 ({len(zim_files)} 件):")
        for i, z in enumerate(zim_files):
            size_gb = z.stat().st_size / (1024 ** 3)
            _info(f"  [{i + 1}] {z}  ({size_gb:.1f} GB)")

        if len(zim_files) == 1:
            zim_path = zim_files[0]
        else:
            _info("")
            choice = input("  使用する番号を選択 [1]: ").strip()
            idx = int(choice) - 1 if choice.isdigit() else 0
            if 0 <= idx < len(zim_files):
                zim_path = zim_files[idx]
            else:
                zim_path = zim_files[0]
        _ok(f"使用 ZIM: {zim_path}")
    else:
        _warn("ZIM ファイルが見つかりません")
        _info("")
        _info("ダウンロード (約12.4GB):")
        _info("  wget -c https://download.kiwix.org/zim/wikipedia/"
              "wikipedia_en_all_mini_2026-03.zim")
        _info("")
        _info("推奨保存先:")
        kiwix_dir = ROOT / "kiwix"
        _info(f"  {kiwix_dir}/")
        _info("")
        _info("ダウンロード完了後に再度 python install.py を実行してください。")
        return True

    # ── kiwix-serve connectivity ──
    if _http_ok("http://localhost:8888/"):
        _ok("kiwix-serve 稼働中 (port 8888)")
    else:
        _info("kiwix-serve が未起動です")
        _info("")
        _info("手動起動:")
        _info(f"  kiwix-serve --port 8888 {zim_path}")
        _info("")

    # ── systemd service registration (optional) ──
    if not kiwix_bin or not zim_path:
        return True

    _info("systemd サービスとして登録すると自動起動できます。")
    if not _ask_yn("systemd サービスを登録しますか？", default=False):
        _info("手動起動で利用可能です。")
        return True

    username = os.environ.get("USER") or os.environ.get("LOGNAME") or "nobody"
    service_content = (
        "[Unit]\n"
        "Description=Kiwix serve — local Wikipedia for MOBIUS MMV\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        f"ExecStart={kiwix_bin} --port 8888 {zim_path}\n"
        f"User={username}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )

    _info("")
    _info("以下の内容で /etc/systemd/system/kiwix-serve.service を作成します:")
    _info("")
    for line in service_content.splitlines():
        _info(f"  {line}")
    _info("")
    _warn("sudo が必要です")

    if _ask_yn("登録を実行しますか？", default=False):
        service_path = "/etc/systemd/system/kiwix-serve.service"
        # Write via sudo tee
        try:
            proc = subprocess.run(
                ["sudo", "tee", service_path],
                input=service_content.encode(),
                capture_output=True,
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.decode().strip())
            _run("sudo systemctl daemon-reload", capture=True)
            _run("sudo systemctl enable kiwix-serve", capture=True)
            _run("sudo systemctl start kiwix-serve", capture=True)
            _ok("kiwix-serve.service を登録・起動しました")
        except Exception as e:
            _fail(f"サービス登録に失敗: {e}")
            _info("手動で設定してください:")
            _info(f"  sudo nano {service_path}")
    else:
        _info("手動起動でも利用可能です:")
        _info(f"  kiwix-serve --port 8888 {zim_path}")

    return True


# ── Step 4: Web Search API ─────────────────────────────────────────────────


def step4_web_search():
    _section(4, "Web 検索 API（任意）")

    _info("Web検索は verify ルートのフォールバックとして使用されます。")
    _info("Kiwix ローカル検索が利用可能な場合、Web検索なしでも基本動作します。")
    _info("")
    _info("推奨: Brave Search API (https://brave.com/search/api/)")
    _info("他の検索プロバイダー（SerpAPI, Vertex AI Search 等）も")
    _info("web_search_adapter.py のインターフェースに準拠すれば使用可能です。")
    print()

    if _ask_skip("Web 検索 API 設定"):
        _warn("スキップしました（任意）")
        return True

    # ── Check existing .env ──
    env_path = ROOT / ".env"
    existing_key = ""
    env_lines_orig = []

    if env_path.exists():
        with open(env_path) as f:
            env_lines_orig = f.readlines()
        for line in env_lines_orig:
            stripped = line.strip()
            if stripped.startswith("WEB_API_KEY="):
                existing_key = stripped.split("=", 1)[1].strip()
            elif stripped.startswith("BRAVE_API_KEY="):
                existing_key = existing_key or stripped.split("=", 1)[1].strip()

    if existing_key:
        masked = existing_key[:4] + "..." + existing_key[-4:] if len(existing_key) > 8 else "***"
        _ok(f"API キー設定済み ({masked})")
        if not _ask_yn("上書きしますか？", default=False):
            _ok("既存のキーを保持します")
            return True

    key = getpass("  API キーを入力 (非表示、Enter でスキップ): ").strip()
    if not key:
        _warn("入力なし。スキップします。")
        return True

    # Write to .env — update WEB_API_KEY line
    new_lines = []
    key_written = False
    for line in env_lines_orig:
        stripped = line.strip()
        if stripped.startswith("WEB_API_KEY="):
            new_lines.append(f"WEB_API_KEY={key}\n")
            key_written = True
        else:
            new_lines.append(line)
    if not key_written:
        new_lines.append(f"WEB_API_KEY={key}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)

    _ok(f".env に WEB_API_KEY を保存しました")
    return True


# ── Step 5: Connectivity check ─────────────────────────────────────────────


def step5_verify():
    _section(5, "疎通確認")

    results = []  # (category, name, status, detail)

    # ── Ollama API ──
    if _http_ok("http://localhost:11434/api/tags"):
        results.append(("必須", "Ollama API (localhost:11434)", "ok", "稼働中"))
    else:
        results.append(("必須", "Ollama API (localhost:11434)", "fail", "未到達"))

    # ── qwen3.5:9b ──
    model_found = False
    try:
        with urllib.request.urlopen(
            "http://localhost:11434/api/tags", timeout=3
        ) as r:
            data = json.loads(r.read())
            models = [m["name"] for m in data.get("models", [])]
            model_found = any("qwen3.5:9b" in m for m in models)
    except Exception:
        pass

    if model_found:
        results.append(("必須", "qwen3.5:9b モデル", "ok", "利用可能"))
    else:
        results.append(("必須", "qwen3.5:9b モデル", "fail", "未検出"))

    # ── Kiwix ──
    if _http_ok("http://localhost:8888/"):
        results.append(("推奨", "Kiwix (localhost:8888)", "ok", "稼働中"))
    else:
        results.append(("推奨", "Kiwix (localhost:8888)", "skip", "未起動"))

    # ── Web Search API ──
    env_path = ROOT / ".env"
    web_key = ""
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("WEB_API_KEY="):
                    web_key = stripped.split("=", 1)[1].strip()
                elif stripped.startswith("BRAVE_API_KEY=") and not web_key:
                    web_key = stripped.split("=", 1)[1].strip()

    if web_key:
        results.append(("任意", "Web Search API キー", "ok", "設定済み"))
    else:
        results.append(("任意", "Web Search API キー", "skip", "未設定"))

    # ── FAISS index ──
    faiss_path = ROOT / "data" / "box_b" / "wiki_index_ivfpq.faiss"
    if faiss_path.exists():
        size_mb = faiss_path.stat().st_size / (1024 ** 2)
        results.append(("推奨", "FAISS index", "ok", f"{size_mb:.0f} MB"))
    else:
        results.append(("推奨", "FAISS index", "skip", f"未検出: {faiss_path}"))

    # ── Display summary ──
    print()
    _info("─── 疎通結果 ───")
    print()

    for category, name, status, detail in results:
        tag = f"[{category}]"
        if status == "ok":
            _ok(f"{tag:6s} {name} — {detail}")
        elif status == "fail":
            _fail(f"{tag:6s} {name} — {detail}")
        else:
            _warn(f"{tag:6s} {name} — {detail}")

    # Check mandatory items
    mandatory_ok = all(
        s == "ok" for cat, _, s, _ in results if cat == "必須"
    )

    print()
    if mandatory_ok:
        _ok("必須コンポーネントはすべて正常です")
    else:
        _fail("必須コンポーネントに問題があります")
        _info("上記の ❌ 項目を解決してください。")

    print()
    _info("ヒント: UIのExplore ONを試してみてください。")
    _info("推論精度が向上し、応答も簡潔になります。")
    _info("動作が不安定な場合（応答が空になる等）はOFFに戻してください。")

    return mandatory_ok


# ── Final summary ──────────────────────────────────────────────────────────


def final_summary():
    print()
    print(f"{'─' * 62}")
    print("  起動コマンド:")
    print(f"{'─' * 62}")
    print()

    in_venv = (
        hasattr(sys, "real_prefix")
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
    )
    print(f"  cd {ROOT}")
    if not in_venv:
        venv_path = ROOT.parent / "venv313"
        if (venv_path / "bin" / "activate").exists():
            print(f"  source {venv_path}/bin/activate")
        else:
            print("  source <venv>/bin/activate")
    print("  python src/ui/app.py")
    print()
    print("  ブラウザで http://localhost:7860 が開きます。")
    print()
    print("=" * 62)
    print("  MOBIUS MMV — セットアップ完了")
    print("=" * 62)
    print()


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    os.chdir(ROOT)
    _banner()

    # Step 1: Python + venv + requirements (必須)
    if not step1_python():
        return

    # Step 2: Ollama + model (必須)
    if not step2_ollama():
        _warn("Ollama は必須です。問題を解決後、再実行してください。")
        if not _ask_yn("それでも続行しますか？", default=False):
            return

    # Step 3: Kiwix (推奨)
    step3_kiwix()

    # Step 4: Web Search API (任意)
    step4_web_search()

    # Step 5: Connectivity check
    step5_verify()

    # Done
    final_summary()


if __name__ == "__main__":
    main()
