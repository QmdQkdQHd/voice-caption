# Voice Caption · v0.2.0

게임·디스코드 음성을 CPU로 인식하고 번역 자막을 띄우는 개인용 데스크톱 앱입니다. **Windows 10/11 x64용 개발 프로토타입**이며 GPU와 Python을 별도로 설치하지 않고 사용할 수 있도록 실행 파일에 필요한 구성요소를 묶었습니다.

**Windows 실행 파일 빌드와 자동 검사를 완료했습니다.** 검사 환경은 GitHub Actions의 Windows Server 2022입니다. 실제 Windows 10/11 PC의 오디오 캡처, 디스코드·발로란트 게임 중 동작과 화면 화자 인식은 별도 검증이 필요합니다.

**[처음 사용하는 친구를 위한 사용설명서](docs/친구용-사용설명서.md)**

[더블클릭해서 읽는 HTML 설명서](docs/친구용-사용설명서.html) · [제작자용 설치·빌드 설명서](read.md) · [검증 기록](docs/VALIDATION.md)

GitHub 저장소: [QmdQkdQHd/voice-caption](https://github.com/QmdQkdQHd/voice-caption) · 공개 저장소

## 실행 파일 받기

친구에게는 제작자가 준비한 **`VoiceCaption-0.2.0-windows-x64.zip`을 직접 전달**하는 방식이 가장 간단합니다. 전체 압축을 푼 뒤 `VoiceCaption` 폴더 안의 **`VoiceCaption.exe`**를 실행하세요. `_internal` 폴더도 함께 있어야 합니다. 최초 실행 후 언어 모델은 앱의 **모델 준비 (최초 다운로드)** 버튼으로 별도로 내려받습니다.

현재 GitHub Releases에는 실행 파일을 게시하지 않았습니다. 직접 전달받기 어렵다면 [성공한 Windows 빌드 기록](https://github.com/QmdQkdQHd/voice-caption/actions/runs/43944802001)에 로그인하여 아래쪽 **Artifacts → VoiceCaption-windows-x64**를 내려받을 수 있습니다. GitHub가 내려주는 바깥 ZIP을 풀면 프로그램 ZIP이 한 번 더 나오므로 **안쪽 `VoiceCaption-0.2.0-windows-x64.zip`도 압축 해제**해야 합니다. 아티팩트가 만료되면 제작자에게 파일을 요청하세요.

첫 검증 빌드의 프로그램 ZIP은 약 **366 MB(349 MiB)**입니다. 모델은 포함하지 않으며 버전에 따라 파일 크기가 달라집니다. GitHub의 **Code → Download ZIP**이나 `source.zip`은 개발용 코드로, 실행 파일 패키지와 다릅니다.

## 파일 안내

| 파일 | 용도 |
|---|---|
| `release/VoiceCaption-0.2.0-windows-x64.zip` | 제작자가 내려받아 보관·전달하는 Windows 실행용 ZIP |
| `release/VoiceCaption-0.2.0-source.zip` | 소스·문서·테스트·빌드 스크립트. EXE 없음 |
| `build-windows.cmd` | 제작자가 Windows에서 실행 파일을 다시 만드는 스크립트 |
| `install-windows.cmd` | Python 소스 실행용 환경 설치 |
| `start-windows.cmd` | 소스 버전 실행 |

`release/`의 ZIP은 Git 소스 커밋에 포함하지 않습니다. 저장소를 내려받는 것만으로 실행용 ZIP이 함께 생기지는 않습니다.

## 주요 기능

- GPU 없이 CPU 음성 인식 + 로컬 번역, 선택적 DeepL 대체 번역
- 무음 기준 발화 분할, 음성 인식과 번역 대기 분리
- 최근 세 발화를 유지하는 자막, 문장 길이에 따른 표시 시간
- 위치·크기·폰트·색상·배경 불투명도·클릭 통과 조절
- 별도 음성 처리 프로세스와 중지 시 정리, 독립 오류 표시
- 사용자 지정 화면 영역과 색상을 사용하는 실험적 화자 이름 OCR

![자막 예시](docs/subtitle-preview.png)

## 처음 실행하기

1. 실행용 ZIP을 전체 압축 해제합니다.
2. `VoiceCaption.exe`를 실행합니다.
3. 원문·번역 언어를 선택하고 **모델 준비 (최초 다운로드)**를 누릅니다.
4. 실제로 듣는 헤드셋·스피커의 `[PC 소리]` 장치를 선택합니다.
5. **시작**을 누릅니다. 처음에는 API와 화면 화자 인식을 꺼둡니다.

친구는 Python 설치나 빌드 명령어 입력 없이 이 경로로 시작합니다. 개발자가 소스를 직접 실행하거나 수정하려면 [read.md](read.md)를 참고하세요.

## 알아둘 제한

현재 캡처는 앱별이 아닌 **출력 장치별**입니다. 같은 장치의 효과음과 음악도 포함됩니다. 화자 인식은 화면 기반 추정이며 정확도를 보장하지 않습니다. 실제 PC별 번역 지연, 게임 성능 영향, Vanguard 호환성은 아직 확인하지 않았습니다. 단축키·트레이·다운로드 취소는 미구현입니다.

## 검증 상태

2026-11-21 문서 검토 기준, [첫 Windows 빌드](https://github.com/QmdQkdQHd/voice-caption/actions/runs/43944802001)에서 자동 테스트 **18개**, 패키징된 EXE의 주요 라이브러리·VAD 로딩과 자식 프로세스 통신, UI 시작 검사를 통과했습니다. 실제 음성 녹음·게임 플레이를 통한 검증과는 구분합니다. 세부 범위와 남은 확인 항목은 [검증 기록](docs/VALIDATION.md)에 남깁니다.

개발 환경의 테스트 명령:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q voice_caption tests scripts packaging
```

## 문서와 라이선스

친구에게는 **[친구용 설명서](docs/친구용-사용설명서.md)**를, 빌드를 담당하는 사람에게는 **[상세 기술 문서](read.md)**를 전달하세요.

사용자 코드의 공개 라이선스는 아직 지정하지 않았습니다. 포함되는 의존 패키지와 모델에는 각각의 라이선스가 적용됩니다. 실행 파일의 공개 Release 발행과 코드 서명은 수행하지 않았습니다.
