# 저지아이즈 마작 매크로

저지아이즈(Judgment)의 마작을 PS5 Remote Play 화면만 보고 대신 칩니다. KamuroGo 완성 목록의 마작 항목(Lullaby·Modern·Tachibana 화료 횟수 등)을 채우는 용도입니다. [psconnector](../psconnector) 위에서 돌아갑니다.

## 하는 일

| 화면 | 판단 |
|---|---|
| 내 차례 (손패 14장) | 샹텐이 가장 낮고 유효패가 가장 많이 남는 패를 골라, 커서를 옮겨 버림 |
| 선택지: 론 / 쯔모 | 받음 |
| 선택지: 리치 | 텐파이일 때만 받고, 텐파이를 유지하는 패를 버림 |
| 선택지: 펑 | 방금 버려진 패가 역패(삼원패·장풍·자풍)면 받고, 아니면 넘김 |
| 선택지: 치 / 깡 | 넘김 (멘젠 유지) |
| 결과·정산 화면 | × 진행 |
| 마작 메뉴 "게임 시작하기" | 다음 게임 시작 (`--games N`이면 N게임 뒤 멈춤) |
| 모르는 패·선택지 | 화면을 `unknown/`에 저장하고 멈춤 → 템플릿에 추가 |

## 화면 읽기 (`mj/vision.py`)

- 손패: 1080p 기준 x = 396 + 73.5 × i, y ≈ 910에 왼쪽부터 정렬. `templates/hand/이름_N.png`와 비교합니다 (실제 대국 화면에서 잘라낸 그림).
- 커서: 다른 패보다 8px 이상 올라온 패. 올라온 패를 모르면 커서를 한 칸 옮겨 내린 뒤 다시 읽습니다.
- 선택지 글자: OCR이 한 글자를 잘못 읽어서(론 → 굴) 글자 모양을 `templates/prompt/`와 비교합니다. 처음 보는 글자는 OCR로 읽고 모양을 저장합니다.
- 펑 대상: 선택지 직전 화면과 비교해 새로 놓인 패를 찾고, 색 구성(검정·빨강·초록·빨강+검정·무늬 없음)으로 손의 대자 후보 중에서 고릅니다.
- 자풍: 이름 옆 배지(`templates/seat/`). 서는 아직 못 봐서, 다른 셋이 아닌 배지를 서로 봅니다.

## 엔진 (`mj/engine.py`)

일반형·치또이·국사 샹텐, 유효패, 버림패 선택, 리치 가능한 버림패. 부로 수를 반영합니다.

## 실행

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
ln -s ~/Project/judgment-mahjong-macro ~/Project/psconnector/macros/judgment-mahjong
```

psconnector-view 바에서 "저지아이즈 마작"을 고르고 ▶. 화질은 1080p여야 합니다. `--dry-run`으로 직접 돌리면 판단만 출력하고 아무것도 누르지 않습니다.

```bash
.venv/bin/python -u main.py --dry-run
```

## 테스트

```bash
.venv/bin/python -m unittest discover tests
```

`samples/`의 실제 화면으로 손패·선택지·결과 화면 인식을 검사합니다.
