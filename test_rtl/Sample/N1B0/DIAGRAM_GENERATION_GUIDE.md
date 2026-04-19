# 2년차 계획 다이어그램 생성 가이드

## 📊 생성할 다이어그램 목록

2025_2year_plan.md 문서에 참조된 PNG 다이어그램들:

| 다이어그램 | 파일명 | 내용 |
|-----------|--------|------|
| Item 1-1 | `fig_item1-1_memory_hierarchy.png` | 메모리 계층 구조 비교 (기존 vs 개선) |
| Item 2-1 | `fig_item2-1_parallel_attention.png` | Parallel Attention Unit 아키텍처 |
| Item 2-2 | `fig_item2-2_sparse_attention.png` | 3가지 Sparse Attention 패턴 |
| Item 2-3 | `fig_item2-3_kv_cache_hierarchy.png` | 계층적 KV-Cache 관리 |
| Item 3-1 | `fig_item3-1_conv_optimization.png` | Sliding Window Conv vs Im2Col |
| Item 3-2 | `fig_item3-2_multiscale_features.png` | 멀티스케일 특성맵 저장소 |
| Item 3-3 | `fig_item3-3_adaptive_precision.png` | 적응형 정밀도 선택 |
| Item 4-1 | `fig_item4-1_dvfs_architecture.png` | DVFS 피드백 제어 루프 |
| Overview | `fig_vla_maturity_roadmap.png` | VLA 성숙도 로드맵 |

---

## 🔧 방법 1: Graphviz 사용 (권장)

Graphviz를 설치하면 DOT 형식의 다이어그램을 PNG로 변환할 수 있습니다.

### 설치

**Ubuntu/Debian:**
```bash
sudo apt-get install graphviz
```

**macOS:**
```bash
brew install graphviz
```

**Windows:**
```bash
choco install graphviz
```

또는 https://graphviz.org/download/ 에서 직접 다운로드

### 실행

```bash
cd /secure_data_from_tt/20260221/DOC/N1B0

# Graphviz를 사용한 생성
python3 generate_diagrams_graphviz.py
```

---

## 🔧 방법 2: Matplotlib 사용

matplotlib이 설치된 환경에서는 다음과 같이 실행:

```bash
# matplotlib 설치 (필요한 경우)
python3 -m pip install matplotlib numpy

# 다이어그램 생성
cd /secure_data_from_tt/20260221/DOC/N1B0
python3 generate_diagrams.py
```

---

## 🔧 방법 3: 온라인 도구 사용

Graphviz를 설치할 수 없는 경우, 온라인 도구를 사용할 수 있습니다:

### Graphviz Online (http://www.webgraphviz.com/)

1. `generate_diagrams_graphviz.py`에서 원하는 다이어그램의 DOT 코드 복사
2. 웹사이트에 붙여넣기
3. PNG로 다운로드

### Mermaid 형식 변환

Mermaid 다이어그램도 지원합니다. 온라인 Mermaid 에디터:
- https://mermaid.live/

---

## 📋 생성된 파일 위치

모든 PNG 다이어그램은 다음 위치에 생성됩니다:

```
/secure_data_from_tt/20260221/DOC/N1B0/fig_*.png
```

### 확인

```bash
ls -lh /secure_data_from_tt/20260221/DOC/N1B0/fig_*.png
```

---

## 📖 문서에서 다이어그램 참조

각 항목의 배경 설명 앞에 다음과 같이 참조됩니다:

```markdown
**📊 다이어그램:** `fig_item1-1_memory_hierarchy.png` 참조
```

---

## 🎨 다이어그램 커스터마이징

### Graphviz로 스타일 변경

`generate_diagrams_graphviz.py`의 DOT 코드 수정:

```dot
node [shape=box, style="filled,rounded", fillcolor="#FF6B6B"];
```

색상 변경:
- `#FF6B6B` - 빨강 (Vision)
- `#4ECDC4` - 초록 (Memory)
- `#FFD700` - 노랑 (Control)
- `#A8E6CF` - 연두 (Improvement)

### 고해상도 PNG 생성

```bash
dot -Tpng -Gdpi=300 -o output.png input.dot
```

---

## ✅ 체크리스트

- [ ] Graphviz/Matplotlib 설치
- [ ] Python 스크립트 실행
- [ ] PNG 파일 생성 확인
- [ ] 2025_2year_plan.md에 이미지 포함 (IDE에서 프리뷰)
- [ ] 고해상도(DPI 300) 버전 생성 (필요시)

---

## 🔗 참고 자료

- **Graphviz 공식:** https://graphviz.org/
- **DOT 언어 문서:** https://graphviz.org/doc/info/lang.html
- **Matplotlib 문서:** https://matplotlib.org/
- **Mermaid (대체 옵션):** https://mermaid.js.org/

---

## 💡 팁

1. **빠른 생성:** Graphviz가 가장 빠름 (~1초/다이어그램)
2. **고품질:** matplotlib으로 더 정교한 그래프 가능
3. **편집 용이:** DOT 코드는 텍스트이므로 버전관리 가능
4. **확장성:** 다이어그램 추가 시 같은 방식으로 확장 가능

---

**마지막 업데이트:** 2026-04-01
