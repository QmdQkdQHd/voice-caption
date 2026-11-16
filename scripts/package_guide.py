"""Build a beginner-friendly offline guide folder and ZIP (no application)."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "release" / "친구용-안내"
    destination.mkdir(parents=True, exist_ok=True)
    content = (ROOT / "docs" / "친구용-사용설명서.html").read_text(encoding="utf-8")
    remote = "https://github.com/QmdQkdQHd/voice-caption/blob/main/"
    content = content.replace('href="../read.md"', f'href="{remote}read.md"')
    content = content.replace('href="VALIDATION.md"', f'href="{remote}docs/VALIDATION.md"')
    (destination / "사용설명서.html").write_text(content, encoding="utf-8")
    for name in ("settings-preview.png", "subtitle-preview.png"):
        shutil.copy2(ROOT / "docs" / name, destination / name)
    (destination / "먼저-읽어주세요.txt").write_text(
        "Voice Caption 사용 설명서\n\n"
        "1. 이 ZIP을 전체 압축 해제하세요.\n"
        "2. 사용설명서.html을 두 번 클릭하세요. 인터넷 브라우저로 열립니다.\n"
        "3. 설명서의 첫 단계부터 따라 읽으세요.\n\n"
        "이 안내 ZIP에는 실행 프로그램이 없습니다.\n"
        "프로그램은 제작자가 Windows에서 빌드한 windows-x64.zip을 별도로 받아야 합니다.\n",
        encoding="utf-8-sig")
    result = shutil.make_archive(str(ROOT / "release" / "VoiceCaption-친구용-사용설명서"),
                                 "zip", destination.parent, destination.name)
    print(result)


if __name__ == "__main__":
    main()
