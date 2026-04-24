# `top200_movies.csv` への修正履歴
**作成者:** Hiroaki | **最終更新:** 2026-04-23(Round-3 audit 追加)

オリジナルの `top200_movies.csv`(初期コミット時点)に対して実施した修正を記録する。修正は **データ品質問題の修正のみ**で、興行収入や監督等のビジネス判断は伴わない(ただし誤記載を Box Office Mojo / IMDb 等の正規ソースに揃え直しているケースはあり)。

修正後の **n = 194**(オリジナル 197 から 3行削除、3行リネーム + 周辺修正、加えて Round-3 wiki audit で 60本の Wikipedia データを CSV を変更せずに修正)。

---

## 1. 行削除(3件)

### 1.1 行80 削除: "DreamWorks Dragons 2" (2014)
- **理由**: 行92 "How to Train Your Dragon 2" (2014) と完全重複。**興行収入が1ドル単位で同一**($618,876,695)、監督・スタジオ・公開年すべて一致
- "DreamWorks Dragons" は Netflix 配信の TV シリーズ(劇場映画ではない)。CSV のスクレイピング段階での誤混入が原因と推測
- 修正コミット: hiroaki `c00162e` / main `99eb503`

### 1.2 行23 削除: "Incredibles" (2004) — Round-3
- **理由**: 行53 "The Incredibles" (2004) と完全重複。**興行収入が1ドル単位で同一**($633,026,024)、監督 Brad Bird も一致
- 公式タイトルは "The Incredibles"(冠詞付き)。重複側("Incredibles")は Wikipedia API がリダイレクトページに当たって langs=0 になっており、本物("The Incredibles" 行53)は langs=74 を取得済みだった
- Round-3 の wiki_views ≤ 10,000 audit 中に発覚
- 修正コミット: hiroaki `20730eb` / main `196d4fe`

### 1.3 行74 削除: "Frozen 2" (2019)
- **理由**: 行13 "Frozen II" (2019) と完全重複。**興行収入 $1,450,026,015 が1ドル単位で同一**、監督・スタジオすべて一致
- "Frozen II"(ローマ数字)が公式タイトル、"Frozen 2"(アラビア数字)は同一作品の別表記
- API クエリ結果が異なるため、両方残しておくと CFI で整合性が取れなくなる
- 残した方("Frozen II")は OMDb で正しいデータ(rating 6.8)を返したのに対し、削除した方("Frozen 2")は OMDb で別作品にヒット(rating 3.9)していた
- 修正コミット: hiroaki `9c7a716` / main `e7fa3f7`

---

## 2. タイトル変更(3件)

### 2.1 行103 リネーム: "Illumination's Pets United" → "The Secret Life of Pets 2"
- **理由**: 元タイトルは TMDB に存在せず、興行 $458M / 2019年 / Illumination という属性が **The Secret Life of Pets 2** と一致
- "Pets United" はドイツ製作の別作品(Netflix配信、劇場興行ほぼゼロ)で、本来 Top 200 に含まれない
- CSV 作成時に正しい作品名がわからず一時的タイトルが残った可能性
- **追加修正**:
  - 興行収入: $458,168,898 → **$431,118,094**(Box Office Mojo 公式)
  - 予算: $75M → **$80M**(Box Office Mojo 公式)
  - 監督: Eric Darnell → **Chris Renaud**(本物の監督)
  - スタジオは Illumination のまま(正しい)
- 修正後にデータ再取得を実施
- 修正コミット: hiroaki `c00162e` / main `99eb503`

### 2.2 行105 リネーム: "Dr. Seuss' Horton Hears a Who!" → "Horton Hears a Who!"
- **理由**: タイトルに含まれる **アポストロフィ + 感嘆符** が Wikipedia / Wikiquote / OMDb の API 検索を破壊していた
  - wiki_views = 722(本物の値は約126万)
  - wiki_langs = 0(本物は49)
  - omdb wins/noms = 0/0(本物は1/4)
  - wikiquote = not_found(本物は23 dl blocks)
- 正しい Wikipedia 記事名は "Horton Hears a Who! (film)" — "Dr. Seuss'" の冠詞を除去すれば正常検索可能
- **追加修正**:
  - 監督: Steve Carell → **Jimmy Hayward**(Steve Carell は声優、監督ではなかった)
  - スタジオ: Illumination → **Blue Sky Studios**(本物の制作会社)
- 修正後にデータ再取得を実施(全6ソース正常取得)
- 修正コミット: hiroaki `9c7a716` / main `e7fa3f7`

### 2.3 行68 リネーム: "The Sleeping Beauty" → "Sleeping Beauty"
- **理由**: タイトル先頭の "The" により、Wikipedia API が **チャイコフスキーのバレエ作品**(同名)のページにリダイレクトされていた
  - wiki_views = 2,683(バレエページのアクセス数 ← 1959年Disney映画ではない)
  - wiki_langs = 0
  - omdb rating = 6.2(別作品にヒット ← 本物は7.2)
- 1959年 Disney 映画の正式 Wikipedia ページは "Sleeping Beauty (1959 film)"(冠詞 "The" なし)
- メタデータ(監督 Clyde Geronimi、スタジオ Disney、興行 $170M、予算 $4M)はすべて1959年Disney版の正しい値だったので **タイトルだけ修正**
- 修正後にデータ再取得を実施:
  - wiki_views: 2,683 → **1,836,599**
  - wiki_langs: 0 → **79**
  - omdb wins: 0 → **3**
  - wikiquote: 0 → **14**
- 修正コミット: hiroaki `e84969b` / main `d787f00`

---

## 3. CSV 修正と関連する追加データ修正

CSV のタイトル誤記がそのまま API 検索の失敗を引き起こすため、以下のスクリプトを開発・適用した(全て `scripts/` 配下、main + hiroaki 両方):

| スクリプト | 役割 | 影響範囲 |
|---|---|---|
| `fix_disambiguation_titles.py` | タイトルに `(年)` が含まれる4本(Lion King 1994/2019、Beauty and the Beast 1991/2017)の wiki/wikiquote/omdb 再取得 | 4本 |
| `fix_wiki_views_bulk.py` | wiki_views ≤ 100 の作品を網羅的に再検索(disambiguation `_(YYYY_film)` URLが空redirectだった作品の修正) | 16本 |
| `fix_csv_errors.py` | 行80削除 + 行103リネーム + 該当作品のデータ再取得 | 2本 |
| `fix_csv_errors_round2.py` | 行74削除 + 行105リネーム + Horton 再取得 | 2本 |

**合計**: 24本の作品で何らかのデータ修正を実施。修正前は壊れた値(0 または near-0)で CFI 計算が歪んでいたが、現状は正常データに置き換わっている。

---

## 4. 修正の影響(主要ランキング変動)

### Before(全修正前)の TOP 10 アンダーパフォーマー
1. DreamWorks Dragons 2(後に**重複削除**)
2. Illumination's Pets United(後に**リネーム**)
3. **The Lion King (1994)** ← データ修正で脱落
4. **The Lion King (2019)** ← データ修正で脱落
5. **Beauty and the Beast (2017)** ← データ修正で脱落
6. The Mummy: Tomb of the Dragon Emperor
7. Dr. Seuss' Horton Hears a Who!(後に**リネーム**)
8. How to Train Your Dragon 3
9. Ant-Man and the Wasp: Quantumania
10. Frozen 2(後に**重複削除**)

### After(全修正後)の TOP 10 アンダーパフォーマー
1. How to Train Your Dragon 3 (2019)
2. Madagascar 3 (2012)
3. The Croods (2013)
4. Frozen II (2019) ← Frozen 2 重複削除後の唯一のエントリ
5. Madagascar 2 (2008)
6. Toy Story 4 (2019)
7. Thor: The Dark World (2013)
8. **🆕 Batman v Superman: Dawn of Justice** — 真のアンダーパフォーマー
9. The Lion King (1994) — データ修正後も中下位(妥当)
10. (後続)

修正前は「データが壊れていただけの作品」が underperformer リストを汚染していたが、**修正後は本物の文化的アンダーパフォーマー(続編疲れ作品 + DC失敗作)が浮上**し、論文ストーリーが正常化した。

---

## 4b. Round-3 audit: wiki_views ≤ 10,000 一括点検(2026-04-23)

Round-1/2 の修正後も §5 で指摘していた「**wiki_views ≤ 10,000 の網羅未実施**」リスクが残っていた。多くの作品は元コレクタが disambiguator URL(`Foo_(YYYY_film)`)を採用していたが、これは canonical 記事へのリダイレクトにすぎず、Wikipedia pageviews API はリダイレクトを追跡しないため、disambig ページの直接アクセスのみが集計され、本来の数百万 views が失われていた。

46本対象の audit (`scripts/audit_low_wiki_views.py`)を実施。Round-3 + 3b で **MediaWiki redirect 解決アプローチ**で修正:`?redirects=true` クエリで Wikipedia 自身のリダイレクト連鎖をたどり、canonical 記事タイトルから pageviews + langlinks を再取得。

### Round-3 (`fix_csv_errors_round3.py`) — wiki_views ≤ 10,000
- "Incredibles" (2004) 重複行を `top200_movies.csv` および `data/*.json/*.csv` 全体から削除("The Incredibles" を canonical として保持)
- **43本**の pageviews + langs を再取得。2本は安全スキップ(Aladdin, Thor — canonical 解決で langlinks が逆に減るため)

### Round-3b (`fix_csv_errors_round3b.py`) — wiki_langs ≤ 5
views 閾値超過だが langlinks が壊れている(langs ≤ 5 なのに有名作)作品を二段目で処理。同じ redirect 解決ロジックだが、canonical の views が既存値の 50% を下回る場合は views を更新せず langs だけ修正。
- **追加 15本** 修正: Avengers (2012) langs 0→84, Snow White (1937) langs 0→113, Mulan (1998) langs 0→77, Lion King (1994) views 47K→5.9M langs 1→114, Lion King (2019) langs 1→56, Oppenheimer (2023) views 15K→51.5M, Rogue One views 165K→4.4M など

### Round-3 manual パッチ
自動修正で悪化する3本は手動で正しい canonical 記事に切り替え:
- **Sing (2016)**: canonical 解決が `Sing_(disambiguation)` に着地。`Sing_(2016_American_film)` に手動修正(views 4828→2,275,929; langs 0→54)
- **Trolls (2016)**: canonical 解決が `Troll`(神話の生物)に着地。`Trolls_(film)` に手動修正(views 31,742→2,037,555; langs 0→41)
- **Aladdin (1992)**: canonical 解決が `Aladdin_(disambiguation)` に着地(Round-3 が正しくスキップした)。`Aladdin_(1992_Disney_film)` に手動修正(views 7758→2,698,063; langs 61→95)

### Round-3 ランキング影響(全修正後 TOP 10)
**アンダーパフォーマー**(Round-3 後):
1. Batman v Superman: Dawn of Justice (2016)
2. How to Train Your Dragon 3 (2019)
3. The Croods: A New Age (2020)
4. Ice Age: Dawn of the Dinosaurs (2009)
5. Madagascar 2 (2008)
6. 101 Dalmatians (1961)
7. Transformers (2007)
8. Thor (2011)
9. Star Wars: The Force Awakens (2015)
10. Trolls (2016)

**オーバーパフォーマー**(Round-3 後):
1. Titanic (1997) — cfi=100
2. Pulp Fiction (1994)
3. **Oppenheimer (2023)** ← 修正で浮上(以前は壊れた wiki データに隠れていた)
4. Dune (2021)
5. Madagascar (2005)
6. Toy Story (1995) — wiki views 修正後に上昇
7. Avengers: Age of Ultron (2015)
8. Inglourious Basterds (2009)
9. Batman Begins (2005)
10. The Incredibles (2004) — 重複削除 + wiki views 修正後に上昇

ML Model B(early reception 含む)の `buzz` CFI は test AUC = 0.859, CV AUC = 0.718 ± 0.094 を達成。Round-3 前と比べて有意に改善。

---

## 5. 残存する潜在的データ品質リスク

Round-3 audit で最大リスクは解消した。残存可能性:

- **wiki_views ≤ 10,000 の作品** — Round-3 で対応済み(主要残存リスク解消)

---

## 6. 監査ログ

修正コミットの完全リスト:

| 修正対象 | hiroaki commit | main commit |
|---|---|---|
| disambiguation 4本 | `99cf85c`(中の一部) | `0a3f89b` |
| wiki_views バルク 16本 | `56dc99a` | `85fdc41` |
| 行80削除 + 行103リネーム + Pets 2 取得 | `c00162e` | `99eb503` |
| Pets 2 reddit 再取得 | `c71cb68` | `31bab79` |
| 行74削除 + 行105リネーム + Horton 取得 | `9c7a716` | `e7fa3f7` |
| 行68リネーム + Sleeping Beauty 取得 | `e84969b` | `d787f00` |
| Round-3: Incredibles 重複削除 + 43本 wiki redirect 解決 | `20730eb` | `196d4fe` |
| Round-3b: 15本 langs ≤ 5 redirect 解決 | (同コミット) | (同コミット) |
| Round-3 manual: Sing / Trolls / Aladdin canonical 修正 | (同コミット) | (同コミット) |

各コミットメッセージに修正の詳細・Before/After 数値・影響を記載してある。`git log --oneline` で追跡可能。
