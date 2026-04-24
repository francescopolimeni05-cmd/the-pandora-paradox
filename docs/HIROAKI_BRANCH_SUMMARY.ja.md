# `hiroaki` ブランチ作業サマリ
**作成者:** Hiroaki | **最終更新:** 2026-04-22

本ドキュメントは `main` ブランチ向けに作成された要約で、**`hiroaki` ブランチで進めた追加作業**を整理したものである。`main` 自体には別途 YouTube 収集スクリプトのみを追加しており、それ以外の拡張作業は `hiroaki` ブランチに隔離されている(チームが確認・検討してからマージするため)。

対象ブランチ: [`origin/hiroaki`](https://github.com/HiroakiNakano1985/capstone-pandora-paradox/tree/hiroaki)

---

## 1. 何をやったかの概要

`main` の [docs/PROGRESS.md](PROGRESS.md) 時点のパイプラインに対し、**3方向の追加作業**を実施した:

1. **新規Xデータソースの追加**(8カテゴリ、総追加特徴量 約70個)
2. **分析手法の高度化**(Transformer感情 / Vonnegut感情アーク / TF-IDF SVD / Sentence埋め込み)
3. **Y変数の再定義実験**(balanced / pure_culture / buzz の3パターン比較)

目的: `main` 時点での Model A 回帰 test R²= -0.010 を改善し、**原案P262 が示唆する「文化的足跡の予測」に近い分析基盤を構築すること**

---

## 2. 追加したXデータソースと特徴量(8カテゴリ)

### 2.1 YouTube トレーラー特徴量 — `scripts/07_youtube_trailer_collector.py`

YouTube Data API v3 経由で公式トレーラーを検索し、**データリーケージを避けるための2バケット分割**:

- **Model A 安全**(スタジオの制作・マーケ決定、公開前に確定)
  - `yt_trailer_count`: 公式トレーラー投稿数(マーケ投資規模のプロキシ)
  - `yt_upload_lead_days`: 初回トレーラーから公開までの日数(キャンペーン期間)
- **Model B 専用**(初期観客反応、post-release)
  - `yt_comments_day_7`, `yt_comments_day_30`, `yt_comments_velocity`

**実装上の制約**(docstring にも明記):
- 2005年以前の映画はスキップ(YouTube自体が存在しない)
- 総コメント数 >5,000 のトレーラーは API の `order=oldest` がないため Day-7 に到達できず NaN
- 大手スタジオ公式トレーラーの約50%はコメント機能を無効化 → NaN
- Social Blade は login 必須で動画単位日次履歴はスクレイピング不可

**カバレッジ**: Day 1 完了分 109/197本(うち87本success)、Day 2(クォータリセット後)で残り77本予定

### 2.2 スターパワー特徴量 — `scripts/08_star_power.py`

TMDB `/movie/{id}/credits` + `/person/{id}/movie_credits` で、**監督・主演・上位3キャストの過去作(公開年<対象年)を集計**。

重要な設計判断: `/person/movie_credits` は revenue を返さないため、代わりに `vote_count` を使用。Vote_count は「関与度」のプロキシとして興行収入より文化浸透との整合性が高いので、**むしろ本プロジェクトに適合**。

| 特徴量 | 意味 |
|---|---|
| `director_past_avg_popularity` | 監督過去作の平均TMDB popularity |
| `director_past_max_vote_count` | 監督のピーク作の投票数 |
| `director_past_avg_rating` | 監督過去作の平均評価 |
| `lead_actor_past_*` | 主演俳優版(同上4指標) |
| `cast_top3_past_*` | 上位3キャストの平均版 |

カバレッジ: 194/197本成功。

### 2.3 公開タイミング派生変数 — `scripts/04_1_build_index.py` 内で導出

APIコール不要。TMDB `release_date`(既取得)から純粋に日付演算:

- `release_month`, `release_quarter`, `release_decade`
- `release_is_summer`, `release_is_holiday_window`, `release_is_awards_window`

**→ Model A の予測因子として最大の寄与度を示した**(詳細は §4)

### 2.4 プロット埋め込み類似度 — `scripts/10_plot_embedding.py`

`sentence-transformers/all-MiniLM-L6-v2` で TMDB あらすじを埋め込み、**Leave-One-Out でCFI上位10%/下位10%プロトタイプとのコサイン類似度**を算出。

| 特徴量 | 意味 |
|---|---|
| `plot_sim_to_top_decile` | 過去ヒット作との類似度 |
| `plot_sim_to_bottom_decile` | 過去凡作との類似度 |
| `plot_hit_vs_flop_gap` | 上位 - 下位 |

実測結果としては効果弱め。TMDB あらすじが50-100語しかないのが原因と推定(改善案: 字幕全文で再埋め込み)。

### 2.5 字幕 TF-IDF + SVD — `scripts/03_4_subtitle_tfidf.py`

全187本の字幕対話コーパスに TF-IDF → `TruncatedSVD(K=20)` で **20個のテーマ軸**を抽出。

`min_df` を映画数の約7%(=13)に設定することで、フランチャイズキャラ名(Jack Sparrow, Woody, Elsa)が主成分を支配する問題を回避。

### 2.6 高度感情 + 7感情分類 — `scripts/03_2_advanced_sentiment.py`

字幕対話に2つの Transformer モデルを適用(最大600行/本を均等サンプリング):

1. **cardiffnlp/twitter-roberta-base-sentiment-latest**: pos/neu/neg 確率
2. **j-hartmann/emotion-english-distilroberta-base**: 7感情(anger/disgust/fear/joy/neutral/sadness/surprise)分類

集約特徴量(17個):
- Sentiment: 極性平均/標準偏差/ピーク, 強ポジ/強ネガ比率
- 7感情: 各感情の平均確率 + 最頻率 + **Shannonエントロピー**(感情多様性)

既存の単語リスト式感情分析(`03_1`)を完全に置換する位置づけ。文脈・否定・強調を正しく処理できる(例: "not bad" → positive)。

### 2.7 感情アーク(Vonnegut形状) — `scripts/03_3_emotional_arc.py`

Reagan et al. (2016) "The emotional arcs of stories are dominated by six basic shapes" の手法を採用。

プロセス:
1. 03_2 の行ごと極性系列を20等分セグメントに集計
2. 移動平均(window=3)でスムージング
3. 6つの理想プロトタイプ(rags_to_riches, tragedy, man_in_hole, icarus, cinderella, oedipus)とコサイン類似度マッチング
4. 軌跡統計(ピーク位置、前半/後半傾き、変動幅、range)抽出

187本の主要アーク分布:
| 形状 | 作品数 |
|---|---|
| man_in_hole | 81 |
| cinderella | 32 |
| rags_to_riches | 30 |
| tragedy | 17 |
| oedipus | 15 |
| icarus | 12 |

Reagan et al. の小説分析と整合(man_in_hole が商業作品で支配的)。

### 2.8 既存スクリプトへの拡張

- `scripts/03_1_subtitle_features.py`: `_dialogue_lines`(SRT全行)を永続化するように変更 → 03_2 / 03_3 / 03_4 がコーパスを共有可能に
- `scripts/04_1_build_index.py`: 上記すべての新CSV/JSONサイドカーをマージ + 公開タイミング派生変数を追加
- `scripts/05_1_ml_model.py`: Model A / B の特徴量グループを大幅拡張

---

## 3. Y変数の再定義実験 — 3パターン比較

### 3.1 動機

`main` ブランチの既存 CFI(`balanced`)は8コンポーネント合成で、**うち60%以上が「一般人気・話題性」**(Wikipedia views, Reddit, TMDB votes, Google Trends)。真の「文化的記憶」(Wikiquote, 言語版数, MEMEポスト)は30%程度。

問題:
- 最強予測因子(`tmdb_popularity`, `imdb_rating`)が buzz 代理指標 → buzz で buzz を予測する循環構造の懸念
- *Pulp Fiction*($214M、MEME性高) が相対的に低スコアで、*Avengers: Endgame*($2.8B、MEME密度低)が上位 → 原案の「パンドラパラドックス」直感と矛盾

### 3.2 3つのCFI定義 — `scripts/04_2_alt_cfi.py`

同じ正規化済みコンポーネントから3つのYを並列計算:

| CFI | 構成 | 意図 |
|---|---|---|
| **balanced** | 20% wiki_views + 10% wiki_langs + 20% reddit + 10% tmdb_votes + 10% gtrends + 10% wikiquote + 10% awards + 10% memes | 既存8コンポーネント、ベースライン |
| **pure_culture** | **40% memes + 30% wikiquote + 20% wiki_langs + 10% awards** | 純粋な文化的記憶。人気度代理をすべて除外 |
| **buzz** | 50% reddit + 30% wiki_views + 20% tmdb_votes | 文化フィルタなしの純粋人気。**ネガティブコントロール** |

### 3.3 CFI間相関

|  | balanced | pure_culture | buzz |
| --- | --- | --- | --- |
| balanced | 1.00 | 0.77 | 0.87 |
| pure_culture | 0.77 | 1.00 | 0.44 |
| buzz | 0.87 | 0.44 | 1.00 |

**balanced は buzz(r=0.87)に寄っている** → 既存CFIが buzz 重心である診断が定量化された。pure_culture と buzz の相関は 0.44 で、両者は本質的に異なる対象を測定している。

### 3.4 予測性能比較 — `scripts/05_2_alt_cfi_eval.py`

すべて n=197、Model A (事前情報のみ) / Model B (+初期反応) で評価:

| Y定義 | Model | 回帰 test R² | 最良 test AUC |
|---|---|---|---|
| balanced | A | +0.095 | 0.714 |
| balanced | B | +0.175 | 0.742 |
| **pure_culture** | **A** | **+0.216** | **0.732** |
| **pure_culture** | **B** | **+0.279** | **0.817** |
| buzz | A | -0.042 | 0.586 |
| buzz | B | -0.130 | 0.641 |

---

## 4. 主要発見と含意

### 4.1 Y の純化は予測しやすさを犠牲にしない

**事前予想**: pure_culture は meme/wikiquote のzero-inflated性で予測困難 → R² 下がる  
**実測**: pure_culture の R² は balanced の **2.3倍**、AUC 0.817 に到達

### 4.2 buzz を予測するのが最も難しい

buzz Y は Model B でも R² が負。**我々の特徴量は buzz を予測する能力がない**。
これは逆説的だが重要: **分析手法が "buzz→buzz" の循環予測になっていない**ことの定量的証拠であり、pure_culture での成功の説得力を上げる。

### 4.3 Y 定義は特徴量エンジニアリングより影響が大きい

この1セッションで 70以上の新特徴量を追加したが、Y を balanced → pure_culture に切り替えるだけで得られた予測精度向上は、特徴量追加の効果より大きかった。

### 4.4 特徴量重要度からの発見(Model A, pure_culture 想定)

カテゴリ別の合計寄与度(TOP30内):

| カテゴリ | 合計重要度 | 代表特徴量 |
|---|---|---|
| Release context | 0.189 | `release_quarter`, `release_month` |
| Emotional arc | 0.113 | `arc_sim_icarus`, `arc_volatility` |
| Advanced sentiment | 0.107 | `emotion_joy_top_ratio`, `emotion_diversity_entropy` |
| Star power | 0.101 | `director_past_avg_popularity` |
| Subtitle TF-IDF | 0.083 | `subtitle_tfidf_svd_01` |
| Plot embedding | 0.011 | `plot_sim_to_top_decile` |

**主要発見**:
- **公開時期(月/四半期)** が最強の予測因子 — スタジオが高期待作品を夏/年末に配置する「スタジオ信頼度プロキシ」として解釈すべき
- **Icarus型感情アーク**(↗↘)が Model A のTOP3特徴量。Reagan et al.の小説分析では man_in_hole型が商業成功と相関するが、**映画では Icarus型が文化浸透と相関**するという独自発見
- **感情多様性エントロピー**が予測因子として寄与 — 幅広い感情範囲の作品が文化に残る傾向

### 4.5 オーバーフィッティングの発生

170特徴量 / n=197 のため、test R² は改善する一方 CV AUC は低下(Model A RF: 0.651 → 0.558)。  
対処案: mutual_information で上位30特徴量に絞る feature selection。

---

## 5. `hiroaki` ブランチの変更ファイル一覧

### 新規スクリプト(8個)
```
scripts/03_2_advanced_sentiment.py
scripts/03_3_emotional_arc.py
scripts/03_4_subtitle_tfidf.py
scripts/04_2_alt_cfi.py
scripts/05_2_alt_cfi_eval.py
scripts/07_youtube_trailer_collector.py    ← main にも追加済
scripts/08_star_power.py
scripts/10_plot_embedding.py
```

### 既存スクリプト修正(3個、破壊変更なし)
```
scripts/03_1_subtitle_features.py          ← _dialogue_lines を永続化
scripts/04_1_build_index.py                ← 新規サイドカーをマージ + 公開タイミング派生
scripts/05_1_ml_model.py                   ← 特徴量グループ拡張
```

### 新規データ出力
```
data/youtube_data.json                     ← 87/197本success (Day 1)
data/star_power.json                       ← 194/197本success
data/plot_embedding.json                   ← 194/197本
data/subtitle_tfidf.csv (+terms.json)      ← 187本
data/advanced_sentiment.csv (+json)        ← 187本
data/emotional_arc.csv                     ← 187本
data/pandora_full_dataset_real_alt_cfi.csv ← 197本 × 194列(3CFI含む)
data/alt_cfi_comparison.json               ← 3CFI × ModelA/B 結果
```

### データ品質修正(2026-04-23、`main` にも反映済)

セッション翌日にアンダーパフォーマー Top10 を確認したところ、**The Lion King (1994)** と **The Lion King (2019)** が pure_culture スコア 0 で並んで現れていた — 明らかにデータ異常。調査の結果、**20本の映画で Wikipedia / Wikiquote / OMDb 検索が壊れていた**ことが判明。2つのパターン:

1. **タイトルに `(年)` サフィックス**(4本): "The Lion King (1994)" などが API 検索を破壊
2. **`_(YYYY_film)` URL が空 redirect**(16本): 元コレクターが「最初に200OKを返した候補」を採用していたが、その候補が月1ビューしか返さない redirect/stub ページだった

`main` に修正スクリプト2本を追加済:
- `scripts/fix_disambiguation_titles.py` — 4本対応
- `scripts/fix_wiki_views_bulk.py` — 16本一般化対応(各候補を試して**最大viewのものを採用**)

代表的な修正前後:

| 作品 | wiki_views (Before → After) | balanced score (Before → After) |
|---|---|---|
| Pulp Fiction | 5 → 7,008,469 | 54.3 → **78.6** |
| Apollo 13 | 1 → 4,509,435 | — |
| Jurassic Park | 1 → 6,288,979 | — |
| The Lion King (1994) | 6 → 47,656 | 6.7 → **42.1** |
| Beauty and the Beast (1991) | 0 → 2,824,793 | 0 → **75.6** |

**修正後の TOP10 (CFI_balanced)**:
- **Pulp Fiction (1994) が #1 オーバーパフォーマー**(残差 +30.6) — 教科書的な Pandora Paradox 事例
- **Beauty and the Beast (1991) が #4 にランクイン**
- *Lion King 1994*, *Lion King 2019*, *Beauty and the Beast 2017* がアンダーパフォーマーから脱落(壊れたデータが原因だったと定量的に確認)
- 新たなアンダーパフォーマー: *Batman v Superman: Dawn of Justice*, *Madagascar 2/3*, *The Croods* — **シリーズ続編の文化的減衰**パターン(初代 Madagascar は #3 オーバーパフォーマーなのに 2/3 は両方アンダーパフォーマー)

**留保事項**: Pulp Fiction の #1 は **欧米圏での圧倒的著名度** が主因(IMDb 8.9、カンヌ・パルム・ドール 1994、アカデミー脚本賞)。我々の CFI は完全に英語圏データソースから構築しており、厳密には **Western cultural footprint** を測定している。本研究は ESADE(スペイン)の研究課題で Western blockbuster 市場が対象のため、この測定方針は意図的かつ妥当。

### 詳細ドキュメント(hiroakiブランチ内)
```
docs/SESSION_2026-04-22.md / .ja.md        ← セッション全体サマリ
docs/CFI_COMPARISON.md / .ja.md            ← 3CFI実験の詳細
docs/DELIVERABLES.ja.md                    ← 最終提出成果物ロードマップ
```

---

## 6. チームへの相談事項

### 6.1 hiroaki ブランチをマージすべきか?

**推奨**: 段階的に。以下の順で検討を:

1. **すぐマージ可**: `07_youtube_trailer_collector.py`(すでに main 済)
2. **レビュー後マージ推奨**: `08_star_power.py`(追加コストゼロ、Model A 安全、194/197本 success)
3. **レビュー後検討**: `03_2` / `03_3` / `03_4`(Transformer系、モデルダウンロード必要、精度向上あり)
4. **議論が必要**: `04_2` / `05_2` と pure_culture CFIを primary Y にすべきか

### 6.2 Y定義を pure_culture に切り替えるか?

**論文のストーリー上の意義**:
- 原案 P262 の「cultural footprint(not box office)」により忠実
- buzz で buzz を予測する循環リスク回避
- Avengers Endgame vs Pulp Fiction の直感が数値と一致(§3 の実測値)

**懸念事項**:
- CV分散が大きい(σ≈0.4)
- meme / wikiquote データに編集者バイアス

### 6.3 オーバーフィッティング対応

170特徴量のまま進むか、feature selection で30特徴量に絞るか。前者は論文で robustness check として有用、後者は primary の CV AUC を回復。

---

## 7. 次のステップ(チーム側で何を決めるか)

| # | 決定事項 | 決裁者 | 期限 |
|---|---|---|---|
| 1 | hiroaki ブランチの段階的マージ方針 | チーム全員 | 次回ミーティング |
| 2 | primary Y を pure_culture に切り替えるか | Francesco + Hiroaki | 同上 |
| 3 | Feature selection 実施有無 | 同上 | 同上 |
| 4 | 可視化(scatterplot / rankings / Avatar case)の担当分配 | 同上 | 同上 |

---

## 8. 付記

本サマリが想定する読者は、**`hiroaki` ブランチを pull せずに main だけを見ているチームメンバー**。詳細は:
- コード: `git checkout hiroaki` または GitHub UI
- 詳細発見: [hiroaki/docs/SESSION_2026-04-22.md](https://github.com/HiroakiNakano1985/capstone-pandora-paradox/blob/hiroaki/docs/SESSION_2026-04-22.md)
- CFI実験詳細: [hiroaki/docs/CFI_COMPARISON.md](https://github.com/HiroakiNakano1985/capstone-pandora-paradox/blob/hiroaki/docs/CFI_COMPARISON.md)
- 最終提出ロードマップ: [hiroaki/docs/DELIVERABLES.ja.md](https://github.com/HiroakiNakano1985/capstone-pandora-paradox/blob/hiroaki/docs/DELIVERABLES.ja.md)
