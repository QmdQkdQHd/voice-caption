"""Explicit model provisioning; no model installation during listening."""
import argparse
from collections import deque


def route(packages, source, target):
    pending = deque([(source, [])])
    seen = {source}
    while pending:
        language, path = pending.popleft()
        if language == target:
            return path
        for package in packages:
            if package.from_code == language and package.to_code not in seen:
                seen.add(package.to_code)
                pending.append((package.to_code, path + [package]))
    raise ValueError(f"설치 가능한 번역 경로가 없습니다: {source} → {target}")


def prepare(source, target, model, status=print):
    import argostranslate.package as package
    from faster_whisper.utils import download_model
    status("음성 인식 모델 다운로드 중…")
    download_model(model)
    if source == target:
        return
    status("번역 모델 목록 확인 중…")
    package.update_package_index()
    path = route(package.get_available_packages(), source, target)
    installed = {(p.from_code, p.to_code) for p in package.get_installed_packages()}
    for item in path:
        if (item.from_code, item.to_code) not in installed:
            status(f"번역 모델 다운로드: {item.from_code} → {item.to_code}")
            package.install_from_path(item.download())
    status("모델 준비 완료")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="en")
    parser.add_argument("--target", default="ko")
    parser.add_argument("--model", choices=["tiny", "base", "small"], default="tiny")
    args = parser.parse_args()
    prepare(args.source, args.target, args.model)


if __name__ == "__main__":
    main()
