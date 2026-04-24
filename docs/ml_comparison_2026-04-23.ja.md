# MLモデル結果 — 3-way比較 (2026-04-23)

`data/model_results_real.json` を3つのブランチ状態で横並び比較した記録。

| 列 | 状態 | ソース |
|---|---|---|
| **main (before)** | `main` のコミット `23df41a`(統合前) | `git show 23df41a:data/model_results_real.json` |
| **midterm-submission** | `origin/midterm-submission`、コミット `91afa6a` | `c:/tmp/pandora-midterm-submission/data/model_results_real.json`(worktree) |
| **main (after)** | `main` のコミット `8c7898a`(統合後) | 現在の `data/model_results_real.json` |

3列とも n = 194 本で統一。**after** 列が現在の `main` の状態。

---

## 0. 3列の差分(読み順)

* **before → midterm-submission** — `midterm-submission` ブランチは、Round-2 / Round-3 のデータ品質監査が `main` に取り込まれる**前**の状態から切られている。n = 194 は同じだが:
  * Round-2 のタイトルリネーム(Horton / Sleeping Beauty / Pets 2)と Round-3 の Wikipediaリダイレクト修正(60本)が欠落している。**重要: これらは `main` 側で私が適用したデータ品質監査であり、根本原因は私が最初に実施したデータ収集(`top200_movies.csv` と `live_api_data.json` の初期収集)に複数の潜在バグ(句読点でAPIが壊れるタイトル、`Sleeping Beauty` が Tchaikovsky のバレエにリダイレクトされる問題、誤ラベル映画の行、ページビューAPIが辿らない disambiguation URL の罠など)が含まれていたこと**。これらのバグは 2026-04-22/23 の監査で `main` 上で発見・修正したもので、`midterm-submission` はその修正前に切られたため、元のバグを丸ごと継承している。責任は私にあり、ブランチ自体に非はない。
  * 上記の具体的症状として、`midterm-submission` では**約60本で wiki_views が壊れている**(例: Inside Out 2 = 1 view、Jurassic Park = 1 view、Pulp Fiction = 5)。根本原因は上記と同じ。
  * Google Trends は SerpAPI 経由で 188/190(共有タイトル中99%)の高カバレッジ。`main` は `pytrends` のレート制限で 13/194(7%)。
  * YouTube のスキーマが異なる: `midterm-submission` は絶対値系 `yt_top_views` / `yt_total_views_top3` / `yt_top_likes`、`main` はスタジオ意思決定系 `yt_trailer_count` / `yt_upload_lead_days` + Day-7/30 コメント数。
  * `midterm-submission` は `reddit_posts` を削除、`wikiquote_count` → `wikiquote_page_size` にリネーム。
* **before → after** — `midterm-submission` ブランチの SerpAPI Trends データを `main` の `live_api_data.json` / `extended_api_data.json` にマージ(カバレッジ 7% → 98%)、ブランチの YouTube再生数コレクターを `04_1_build_index.py` の新しい入力として追加、そして新しい4つの再生数関連列を `05_1_ml_model.py` の `YOUTUBE_EARLY_FEATURES` に追加した。`main` の Round-2/3 Wiki 修正と既存の Day-7/30 列は**そのまま保持**。

---

## 1. 数値を読む前の重要な注意

**`n_positive`(オーバーパフォーマーの数)が3列で異なる**: 95 / 113 / 97。なぜ重要か:

分類ターゲットは `is_overperformer = (cfi_residual > 0).astype(int)`、ここで `cfi_residual = cfi_score − cfi_predicted_from_log_gross_log_budget`。`cfi_residual` の符号は CFI components(Wiki views、Reddit、TMDB投票、Google Trends、受賞、引用、メーム)全体に依存する。これらの入力が変われば(`midterm-submission` = 壊れた Wiki + 実 Trends、`main-after` = 修正済み Wiki + 実 Trends)、**`cfi_score` が動き、`cfi_residual` が動き、ゼロを跨ぐ作品が変わる**。

したがって列間の単純な AUC 比較はノイジー — モデルが解いている問題が少しずつ違う。**CV AUC(より安定)を見て、移動方向を読む**。絶対値の差分を深追いしない。

---

## 2. 回帰 — `cfi_score` (0–100) の予測

| Model | 指標 | main (before) | midterm-submission | main (after) |
|---|---|---:|---:|---:|
| A(厳密事前) | test R² | −0.133 | −0.552 | **−0.302** |
| A(厳密事前) | test RMSE | 18.78 | 19.51 | 20.94 |
| A(厳密事前) | CV R² | −0.932 ± 0.521 | **−0.319 ± 0.131** | −0.872 ± 0.813 |
| B(+早期反応) | test R² | **+0.101** | −0.323 | −0.218 |
| B(+早期反応) | test RMSE | 16.72 | 18.01 | 20.26 |
| B(+早期反応) | CV R² | −0.193 ± 0.477 | **−0.037 ± 0.113** | −0.182 ± 0.440 |

**読み取り**: `cfi_score` に対する回帰 R² は3列とも負〜ゼロ付近で変わらない — 「production-side の特徴量は CFI のマグニチュードを予測しない」という Pandora-Paradox の核心所見は**データの違いに頑健**。`midterm-submission` の CV R² が若干マシに見えるのは、私が元々収集したデータ(監査前)の壊れた Wiki 信号が CFI の分散を圧縮している副作用 — 残差分散の分母が小さくなるため、平均予測子に対する相対指標としての R² が punitive ではなくなる。

---

## 3. 分類 — `is_overperformer ∈ {0,1}`

### Model A(厳密事前予測)

| アルゴリズム | 指標 | main (before) | midterm-submission | main (after) |
|---|---|---:|---:|---:|
| XGBoost | test AUC | 0.424 | 0.568 | 0.497 |
| XGBoost | CV AUC | 0.326 ± 0.050 | 0.545 ± 0.073 | 0.341 ± 0.050 |
| RandomForest | test AUC | 0.418 | 0.698 | 0.576 |
| RandomForest | CV AUC | 0.374 ± 0.077 | **0.625 ± 0.038** | 0.390 ± 0.037 |
| LogReg | test AUC | 0.595 | 0.641 | **0.742** |
| LogReg | CV AUC | 0.498 ± 0.065 | 0.594 ± 0.076 | 0.503 ± 0.070 |
| ベストモデル(test AUC) | — | LogReg | RandomForest | LogReg |

### Model B(事前 + 早期反応)

| アルゴリズム | 指標 | main (before) | midterm-submission | main (after) |
|---|---|---:|---:|---:|
| XGBoost | test AUC | 0.684 | 0.622 | **0.821** |
| XGBoost | CV AUC | 0.554 ± 0.075 | 0.661 ± 0.074 | 0.580 ± 0.053 |
| RandomForest | test AUC | 0.700 | 0.720 | 0.795 |
| RandomForest | CV AUC | 0.603 ± 0.039 | **0.737 ± 0.033** | 0.631 ± 0.055 |
| LogReg | test AUC | 0.766 | 0.630 | 0.745 |
| LogReg | CV AUC | 0.637 ± 0.043 | 0.641 ± 0.083 | **0.668 ± 0.050** |
| ベストモデル(test AUC) | — | LogReg | RandomForest | XGBoost |

**読み取り**:
- **Model A**: `main-after` だけが LogReg test AUC 0.70 を超えている(0.742)。ただし CV AUC は before から +0.005 しか動いていない — test AUC の上昇分の大半は、ターゲットが少し変わった状態での 80/20 分割の分散。`midterm-submission` の RandomForest CV(0.625)は `main-after` の RF CV(0.390)を上回るが、これはターゲット依存 — `n_positive` が 113(n の58%)とバランスが良く、RF のバギングがヒットしやすい問題になっている。この `n_positive = 113` 自体、私が元々収集したデータ(監査前)の壊れた Wiki が `cfi_score` を歪めて残差分布が偏った副作用。
- **Model B**: `main-after` で LogReg CV AUC が 0.668 ± 0.050(before の 0.637 ± 0.043 から上昇) — 同じアルゴリズムで特徴量とターゲットだけが変わった、最もクリーンな apples-to-apples の比較。`main-after` の XGBoost test AUC は 0.821 で新ベスト、ただし CV は 0.580 まで落ちている(分散警告)。`midterm-submission` の RF CV AUC 0.737 はそのブランチでの最高値だが、`cfi_score` が**私が元々収集したデータ(監査前の状態)**に対して計算されているため、ターゲット自体が歪んでいる — *この数値は他の2列と like-for-like 比較できない*。

---

## 4. `n_positive` とターゲット分布

| | main (before) | midterm-submission | main (after) |
|---|---:|---:|---:|
| `n_total` | 194 | 194 | 194 |
| `n_positive`(オーバーパフォーマー) | 95 (49%) | **113 (58%)** | 97 (50%) |
| CFI 重み付け | extended | extended | extended |
| `cultural_category` — Strong Overperformer | 37 | 25 | 42 |
| `cultural_category` — Overperformer | 38 | 61 | 35 |
| `cultural_category` — As Expected | 43 | 48 | 35 |
| `cultural_category` — Underperformer | 39 | 30 | 38 |
| `cultural_category` — Strong Underperformer | 37 | 30 | 44 |

`midterm-submission` の分布は中央2バケット(86 = Over + As Expected)に偏っており、`main` のバイモーダルな分布と対照的。直接原因: 私の監査前データ収集から継承された壊れた Wiki 信号が `cfi_score` レンジを圧縮し、作品が残差境界付近に密集している。

---

## 5. モデルごとの特徴量セット(Xに実際何が入っているか)

| 特徴量グループ | before | midterm-submission | after | Notes |
|---|:-:|:-:|:-:|---|
| メタデータ (7) | ✅ | ✅ | ✅ | `budget`, `is_sequel`, `is_animated`, `has_franchise`, `genre_encoded`, `year`, `years_since_release` |
| 字幕NLP (19) | ✅ | ✅ | ✅ | 3列共通 |
| `yt_trailer_count`, `yt_upload_lead_days` (Model A) | ✅ | ❌ | ✅ | `midterm-submission` はスタジオ側YTなし |
| `yt_comments_day_7/30/velocity` (Model B) | ✅ | ❌ | ✅ | `midterm-submission` は Day-7/30 なし |
| `yt_top_views`, `yt_total_views_top3`, `yt_top_likes`, `yt_top_comments_total` (Model B) | ❌ | ✅(名前違い) | ✅ | `midterm-submission` の列名: `yt_top_views`, `yt_total_views_top3`, `yt_top_likes`, `yt_top_comments` |
| `tmdb_vote_average`, `tmdb_popularity`, `imdb_rating`, `metascore` (Model B) | ✅ | ✅ | ✅ | 3列共通 |
| **使用特徴量数 — Model A** | 28 | 27 | 28 | |
| **使用特徴量数 — Model B** | 35 | 36 | **39** | `main-after` = 両YT手法のスーパーセット |

---

## 6. 主要CFI入力のカバレッジ差分

| 特徴量 | main (before) | midterm-submission | main (after) |
|---|---:|---:|---:|
| `gtrends_avg_interest` | 13/194 (7%) | **188/190 (99%)**(共有タイトル) | **190/194 (98%)** |
| `yt_trailer_count` | 161/194 (83%) | — | 161/194 (83%) |
| `yt_comments_day_7/30` | 42/194 (22%) | — | 30/194 (15%)(重複削除後) |
| `yt_top_views` | — | 190/190 (100%)(共有) | **192/194 (99%)** |
| `yt_top_likes` | — | 188/190 (99%)(共有) | 190/194 (98%) |
| Wiki views(canonical値以上) | 194/194 (100%) | **約60本で ≤ 50 views**(壊れ) | 194/194 (100%) |
| `wiki_languages`(非ゼロ) | 194/194 | 119/194(75本欠落) | 194/194 |

`midterm-submission` 列の「壊れた」Wiki 数値は、**私が元々行ったデータ収集(Round-2/3 監査前)から継承されたもの**。ブランチの構築方法の問題ではなく、ブランチは私が渡したデータをそのまま引き継いでいるだけ。

---

## 7. 上位5特徴量(回帰重要度)

| 順位 | main (before) — Model A | midterm-submission — Model A | main (after) — Model A |
|:-:|---|---|---|
| 1 | `short_punchy_count` 0.167 | `genre_encoded` 0.089 | `short_punchy_count` 0.161 |
| 2 | `rare_proper_noun_count` 0.097 | `rare_proper_noun_count` 0.084 | `sentiment_spike` 0.088 |
| 3 | `humor_indicator` 0.068 | `violence_indicator` 0.074 | `rare_proper_noun_count` 0.075 |
| 4 | `vocabulary_richness` 0.055 | `exclamation_ratio` 0.072 | `short_punchy_density` 0.057 |
| 5 | `violence_indicator` 0.045 | `vocabulary_richness` 0.072 | `humor_indicator` 0.057 |

Main の Model A は before/after とも同じメーム型テンプレート / 造語名の脚本プロキシが支配。`midterm-submission` の Model A は重要度が平坦(どの特徴量も 0.09 に到達しない) — 監査前の私のデータ収集由来の壊れた Wiki 信号が Y 分散を圧縮している結果として整合的。

| 順位 | main (before) — Model B | midterm-submission — Model B | main (after) — Model B |
|:-:|---|---|---|
| 1 | `tmdb_popularity` 0.206 | `imdb_rating` 0.187 | `tmdb_popularity` **0.273** |
| 2 | `imdb_rating` 0.143 | `tmdb_popularity` 0.106 | `metascore` 0.063 |
| 3 | `tmdb_vote_average` 0.086 | `yt_top_comments` 0.083 | `imdb_rating` 0.061 |
| 4 | `rare_proper_noun_count` 0.047 | `metascore` 0.073 | **`yt_comments_day_7` 0.060** |
| 5 | `vocabulary_richness` 0.047 | `rare_proper_noun_count` 0.057 | `tmdb_vote_average` 0.057 |

`main-after` の Model B: `tmdb_popularity` の集中度が上昇(0.206 → 0.273 — ターゲットがクリーンになった分レバレッジが増した?)、さらに **`yt_comments_day_7`**(main 独自の Day-7 コメントカウント)が top-5 入り — 30/194 のカバレッジしかないが、30本の中での信号が強くツリーモデルが掴みに行っている。`midterm-submission` 側の等価物 `yt_top_comments`(再生側の累計)も top-3 に入っており、YouTube コメント量はどの集約方法でも信号を持つことが確認できる。

---

## 8. まとめ

1. **`midterm-submission` ブランチの SerpAPI Trends コレクターが、このブランチから取り入れる最も価値の高い追加物**。これを採用することで `main` の Trends カバレッジが 7% → 98% に跳ね上がる。Trends は X側 の特徴量ではなく CFI component(Y側)なので、見かけの AUC ジャンプよりも効果は subtle — ただし「CFI 残差ターゲットが、もはやスパースなゼロ列ではなく実信号から計算される」という根本的な改善がある。
2. **ブランチの YouTube再生数コレクターは Model B の早期反応サイドを強化**する。既存の Day-7/30 列が 22% しか到達できなかったのに対し、再生数系は192/194(ほぼ全件)。Model B の LogReg CV AUC が **0.637 → 0.668** とこの入力変更のみで動く。
3. **`midterm-submission` の分類数値(例: RF CV AUC 0.737)は `main` のベンチマークとして直接使えない** — *これはブランチに非があるのではない*。監査前の私のオリジナルデータ収集から切られたため、その時点で約60本の Wikipedia 信号が壊れていた(不正なリダイレクト、`top200_movies.csv` のタイトル誤記・句読点破壊、誤ラベル行)。これらのバグは私の責任で、`main` 上の 2026-04-22/23 監査で修正したが、その時点では `midterm-submission` ブランチは既に切られていた。結果として、ブランチ側の `cfi_score` / `cfi_residual` / `is_overperformer` はすべて歪んだYに対して計算されている。報告すべきは `main` 側の Y 構築(Round-2/3 監査後 + SerpAPI Trends)。
4. **Model A は CV AUC ≈ 偶然レベルに留まる** — 3列すべてで。production-side データが文化的フットプリントを pre-determine しないという Pandora Paradox の核心所見は、試したすべてのデータ品質摂動に耐えた。
5. 残差をターゲットにする probe(2026-04-23 ミーティングブリーフ §4.5 参照)は `cfi_score` ターゲットよりも研究質問に忠実。論文提出前に `main-after` で再実行する価値がある。
