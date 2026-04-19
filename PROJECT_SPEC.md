# 語音聽寫工具 - 專案規格文件

## 專案概述

打造一個完全本機運行、完全免費、注重隱私的 Windows 語音聽寫桌面工具。類似 Wispr Flow 和 Typeless,但所有處理都在本機完成,語音資料永不離開使用者的電腦。

**核心使用流程:**
1. 使用者按住熱鍵(預設右 Ctrl,可在設定檔自訂)
2. 程式錄製麥克風音訊
3. 使用者放開熱鍵,程式停止錄音
4. 本機 Whisper 模型將音訊轉為文字
5. (未來擴充)本機 LLM 清理贅字並潤飾
6. 文字自動貼到游標所在的文字欄位

---

## 技術選型

| 元件 | 選用技術 | 理由 |
|---|---|---|
| 語言 | Python 3.10+ | 使用者熟悉,套件齊全 |
| 語音辨識 | faster-whisper | 比原版 Whisper 快 4 倍,支援 CPU int8 量化 |
| 音訊錄製 | sounddevice | 跨平台、穩定、支援 callback |
| 熱鍵監聽 | keyboard + 備用方案 | 見下方「熱鍵實作細節」 |
| 文字輸出 | pyperclip + keyboard | 中文無法用 keyboard.write,改用剪貼簿+Ctrl+V(Ctrl+V 走 `keyboard.send`,比 pyautogui 在 IME 啟用時可靠) |
| 系統匣 | pystray | 讓程式常駐背景,有圖示可控制 |
| 設定檔 | JSON (存在專案資料夾) | 簡單直接,使用者可手動編輯 |
| 打包 | PyInstaller | 可選,用於產生 .exe |

**完全不使用**:OpenAI API、Groq API、雲端服務、任何需要 API Key 的東西。

---

## 重要限制:不做全域安裝

使用者**不希望污染全域 Python 環境**。所有相依套件必須安裝在專案內的虛擬環境(venv)中。

**設定方式:**

```powershell
# 在專案根目錄
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

專案執行時必須啟用 venv。建議提供兩個批次檔:
- `setup.bat` - 建立 venv 並安裝相依
- `run.bat` - 啟用 venv 並執行程式

所有 Python 指令在文件中應寫清楚是在 venv 中執行。

---

## 熱鍵實作細節

### 預設熱鍵:右 Ctrl (`right ctrl`)

選用右 Ctrl 的理由:
- 所有鍵盤都有,通用性最高
- 右 Ctrl 在日常使用中幾乎不會被按到(Ctrl 快捷鍵多用左 Ctrl)
- 不跟任何系統功能衝突(Ctrl 單獨按不會觸發任何系統動作)
- 不需特殊處理(不像 Caps Lock 需要攔截預設行為)
- 符合人體工學:左手繼續打字或操作滑鼠,右手按住說話

### 備選熱鍵(使用者可在 config.json 改)

若使用者想換,以下是可靠的替代選項:
- `caps lock` — 左手小指好按,但需處理大小寫鎖定的預設行為
- `right alt` — 右手大拇指可按,但某些輸入法會把它當 AltGr 使用
- `f9` — 功能鍵,位置較遠但絕對無衝突
- `scroll lock` / `pause` — 幾乎沒人用的鍵,但位置不方便

**不建議**的熱鍵:
- 任何單獨的 Shift — 打字時會大量誤觸
- 左 Ctrl / 左 Alt — 會跟系統快捷鍵衝突
- Win 鍵 — 會觸發開始選單
- Space / Enter — 顯然會干擾正常打字

### 設定檔格式

在 `config.json` 中:
```json
{
  "hotkey": "right ctrl",
  "hotkey_mode": "hold"
}
```

`hotkey_mode` 有兩種:
- `"hold"` - 按住說話,放開轉錄(預設,更直覺)
- `"toggle"` - 按一下開始,再按一下結束

### 實作注意事項

1. **綁定失敗的處理**:若使用者設定的熱鍵無法綁定(罕見,但可能發生),在終端機顯示清楚的錯誤訊息並退回預設的 `right ctrl`。

2. **區分左右 Ctrl**:`keyboard` 套件支援 `right ctrl` / `left ctrl` / `ctrl` 三種綁定。本專案用 `right ctrl`,不要用籠統的 `ctrl`(那會同時綁左右,會跟 Ctrl+C、Ctrl+V 等衝突)。

3. **scancode 方式(可選)**:若字串綁定遇到問題,可改用 scancode(右 Ctrl 在 Windows 上通常是 `0xE01D`)。

4. **避免 Caps Lock 的陷阱**:如果使用者設定成 Caps Lock,要額外用 `keyboard.block_key()` 阻止大小寫切換,否則每次按都會切換狀態。這個細節要在程式中實作。

---

## 功能需求

### 必做(MVP)

1. **熱鍵錄音**
   - 監聽使用者設定的熱鍵
   - 支援 hold 模式:按住錄音、放開轉錄
   - 在終端機顯示錄音狀態

2. **本機語音辨識**
   - 使用 faster-whisper
   - 預設模型:`medium`(平衡速度與準確度)
   - 預設語言:`zh`(中文)
   - 支援 CPU int8 推論(低階電腦也能跑)
   - 自動偵測是否有 CUDA,有則使用

3. **文字輸出**
   - 轉錄完成後,自動貼到游標位置
   - 做法:複製到剪貼簿 → 模擬 Ctrl+V
   - 注意:必須保留使用者原有剪貼簿內容,貼上後還原(使用者體驗)

4. **設定檔**
   - JSON 格式,存在 `config.json`
   - 可設定:熱鍵、模型大小、語言、輸出語系(繁/簡)
   - 首次啟動若無 config.json,自動建立預設版

5. **繁體中文支援**
   - 使用 OpenCC 做簡轉繁(Whisper 輸出常混簡體)
   - 預設轉換模式:`s2twp`(簡體 → 台灣繁體含慣用詞)

### 暫不實作(未來再考慮)

6. **AI 潤飾(本機 LLM)** — 使用者確認暫緩
   - 原本規劃整合 Ollama 做贅字清理與潤飾
   - 考量一般筆電的資源負擔(額外 3-6 GB RAM、總等待時間會從 3 秒拉長到 8-10 秒),第一版先不做
   - 改用 Whisper 的 `initial_prompt` 引導較乾淨的輸出
   - 若未來要加入,在 `config.json` 新增 `refinement` 區塊即可,程式讀取時用 `config.setdefault('refinement', {...})` 填入預設值

### 建議做(加分)

7. **系統匣圖示**
   - 使用 pystray
   - 右鍵選單:啟用/停用、重新載入設定、離開
   - 程式可常駐背景,不需要保留終端機視窗

8. **轉錄歷史**
   - 每次轉錄結果存到 `history.jsonl`(JSON Lines 格式)
   - 包含時間戳、辨識文字、音訊長度、模型名稱
   - 只存本機,使用者可自行刪除

### 不做

- 雲端同步
- 多裝置
- 任何聯網上傳
- 多語言自動切換(固定中文,使用者可在 config 改)
- 圖形化設定視窗(第一版用 JSON 編輯即可)

---

## 專案結構

```
voice_dictation/
├── .venv/                      # 虛擬環境(gitignore)
├── src/
│   ├── __init__.py
│   ├── main.py                 # 進入點
│   ├── config.py               # 設定讀寫
│   ├── recorder.py             # 音訊錄製
│   ├── transcriber.py          # Whisper 語音辨識
│   ├── text_injector.py        # 文字貼到游標位置
│   ├── hotkey_manager.py       # 熱鍵綁定
│   ├── tray.py                 # 系統匣(可選)
│   └── history.py              # 轉錄歷史
├── config.json                 # 設定檔(首次啟動自動建立)
├── history.jsonl               # 轉錄歷史(gitignore)
├── requirements.txt
├── setup.bat                   # 建 venv + 裝套件
├── run.bat                     # 啟動程式
├── README.md
└── .gitignore
```

---

## requirements.txt

```
faster-whisper>=1.0.0
sounddevice>=0.4.6
numpy>=1.24.0
keyboard>=0.13.5
pyperclip>=1.8.2
# 純 Python 版,不需 C++ 編譯。勿與同名的 C 版 `opencc` 同時安裝
opencc-python-reimplemented>=0.1.7
pystray>=0.19.4
Pillow>=10.0.0
```

---

## config.json 預設值

```json
{
  "hotkey": "right ctrl",
  "hotkey_mode": "hold",
  "whisper": {
    "model_size": "medium",
    "language": "zh",
    "device": "auto",
    "compute_type": "int8",
    "initial_prompt": "以下是一段正式的繁體中文。說話者會講完整的句子並使用適當標點符號。"
  },
  "output": {
    "convert_to_traditional": true,
    "opencc_mode": "s2twp",
    "preserve_clipboard": true
  },
  "history": {
    "enabled": true,
    "file": "history.jsonl"
  },
  "tray": {
    "enabled": true
  }
}
```

---

## 各模組功能說明

### `config.py`
- `load_config()` - 讀取 config.json,不存在則建立預設
- `save_config(cfg)` - 寫回檔案
- 使用 `dataclass` 或 `pydantic` 做 schema 驗證
- 所有模組透過這支存取設定,避免散落

### `recorder.py`
- `Recorder` class,用 `sounddevice.InputStream` 非同步錄音
- `start()` / `stop()` 方法
- `stop()` 回傳 numpy array(float32, mono, 16kHz)
- 靜音或過短(< 0.3 秒)時回傳 None

### `transcriber.py`
- `Transcriber` class,啟動時載入 Whisper 模型(約需幾秒)
- `transcribe(audio: np.ndarray) -> str` 方法
- 使用 `vad_filter=True` 自動過濾靜音段
- 使用 `initial_prompt` 引導繁體輸出
- 若啟用轉繁,用 OpenCC 後處理

### `refiner.py`(暫不實作)
- 此模組在第一版不實作,保留做未來擴充
- 若未來要加入,整合方式:
  - 透過 HTTP POST 呼叫 Ollama `/api/generate` 端點
  - Prompt 要求 LLM 去除贅字、修正自我修正、加標點
  - Timeout 處理:超時或連線失敗時回傳原文
  - 在 `main.py` 的轉錄流程中,於 OpenCC 之前插入一層 refine

### `text_injector.py`
- `inject(text: str)` 方法
- 步驟:
  1. 儲存當前剪貼簿內容(若啟用 `preserve_clipboard`;注意:`pyperclip` 只能保留純文字,原先若為圖片/檔案/富文本會失去格式)
  2. 將新文字寫入剪貼簿
  3. 短暫延遲(50ms)確保剪貼簿已更新
  4. 使用 `keyboard.send('ctrl+v')` 模擬 Ctrl+V(走 SendInput scancode,比 pyautogui 的 VK code 在中文 IME 啟用時可靠,不會被 IME 攔截成輸入字元 v)
  5. 短暫延遲(100ms)
  6. 還原原剪貼簿內容

### `hotkey_manager.py`
- `HotkeyManager` class
- 預設綁定 `right ctrl`(注意要用 `right ctrl` 而非 `ctrl`,以免跟左 Ctrl 的系統快捷鍵衝突)
- 啟動時檢查熱鍵是否可綁定
- 若熱鍵綁定失敗,log 錯誤並退回預設 `right ctrl`
- 若使用者設定的是 Caps Lock,需額外用 `keyboard.block_key("caps lock")` 阻止大小寫切換
- 提供 `on_press` 和 `on_release` callback 接口

### `tray.py`
- 用 pystray 建立系統匣圖示
- 圖示用簡單的 PIL 產生(一個麥克風的色塊即可)
- 選單項目:
  - 狀態顯示(如「就緒」、「錄音中」)
  - 啟用/停用聽寫
  - 打開設定資料夾
  - 離開
- 此模組應為可選,若 `config.tray.enabled = false` 則不啟動

### `history.py`
- `append(entry: dict)` - 把 dict 寫成一行 JSON
- entry 結構:
  ```json
  {
    "timestamp": "2026-04-19T14:30:00",
    "duration_seconds": 3.2,
    "text": "辨識結果",
    "model": "medium"
  }
  ```

### `main.py`
- 載入 config
- 初始化各模組(Recorder、Transcriber、TextInjector、HotkeyManager)
- 啟動音訊串流
- 綁定熱鍵
- 啟動系統匣(若啟用)
- 主迴圈:等待 Esc 鍵結束,或系統匣選單點離開

#### 執行緒架構(重要)

三個套件都是背景執行緒/阻塞模型,callback 內必須立刻返回,不能做長任務(否則會卡住 hook):

```
主執行緒       : pystray.Icon.run()(阻塞;Phase 1 無 tray 時改成 keyboard.wait('esc'))
背景 worker    : 一個 queue.Queue,依序處理「轉錄任務」(Transcriber + TextInjector)
keyboard hook  : on_press/on_release 只做 Recorder.start/stop,stop 時把 audio 丟進 queue
sounddevice cb : 只把音訊寫入 buffer,不做任何其他事
```

關鍵約束:
- 轉錄耗時 2-4 秒,**絕對不能**在 keyboard callback 內做,否則整個鍵盤 hook 會延遲/卡死。
- sounddevice callback 在即時音訊執行緒,任何慢動作(print、I/O)都可能造成錄音破音。
- 共享狀態(如「是否錄音中」的 flag)要用 `threading.Lock` 保護。

---

## 熱鍵流程圖

```
使用者按下熱鍵
    │
    ▼
檢查是否已在錄音 ──是──> 忽略
    │
    否
    │
    ▼
Recorder.start()
    │
    ▼
使用者說話(音訊持續寫入 buffer)
    │
    ▼
使用者放開熱鍵
    │
    ▼
Recorder.stop() → audio array
    │
    ▼
音訊太短? ──是──> 略過
    │
    否
    │
    ▼
Transcriber.transcribe(audio) → text
    │
    ▼
OpenCC 簡轉繁(若啟用)
    │
    ▼
TextInjector.inject(text)
    │
    ▼
History.append(...)
```

> 註:未來若加入 Ollama AI 潤飾,會在 OpenCC 轉換前加入一層 `Refiner.refine(text)` 處理,並在連線失敗時自動退回原文。

---

## 錯誤處理原則

1. **模型載入失敗**:終端機顯示清楚錯誤,程式退出(無法繼續)
2. **麥克風不可用**:清楚提示,但程式繼續跑,等使用者插入麥克風後重試
3. **熱鍵無法綁定**:退回預設 `right ctrl`,顯示警告
4. **Whisper 轉錄失敗**:記錄錯誤,貼上空字串(等於無動作),不崩潰
5. **剪貼簿操作失敗**:記錄錯誤,不崩潰

---

## 效能目標

以下為參考值(Whisper medium 模型,約 5 秒中文音訊):

| 硬體 | 轉錄時間 |
|---|---|
| CPU (i5-8代以上) + int8 | 2-4 秒 |
| NVIDIA GPU + float16 | <1 秒 |
| Apple Silicon(未來若支援 Mac) | <1 秒 |

若轉錄太慢,使用者可在 config 改成 `small` 甚至 `base` 模型。

---

## README.md 應包含內容

1. 專案介紹、特色(100% 本機、免費、隱私)
2. 系統需求(Windows 10/11、Python 3.10+、至少 4GB RAM)
3. 安裝步驟(三步:clone → setup.bat → run.bat)
4. 使用方式(熱鍵說明、第一次使用會下載模型等)
5. 設定說明(逐項解釋 config.json)
6. 疑難排解
   - 熱鍵沒反應(可能被別的軟體佔用,或需要系統管理員權限執行)
   - **在工作管理員 / regedit / 以管理員身分執行的視窗內熱鍵無反應**:Windows 安全隔離會阻擋一般程式監聽提升權限視窗的鍵盤事件。解法:以管理員身分執行本工具。
   - **右 Ctrl 被其他軟體佔用**:VirtualBox 預設 Host Key 是右 Ctrl;部分 FPS 遊戲、某些中文輸入法也會用到。若衝突,請在 `config.json` 改熱鍵為 `f9` 或 `caps lock`。
   - **貼上變成字元 v 或沒貼上**:通常發生在中文 IME 啟用時的 Ctrl+V 被攔截。本工具使用 `keyboard.send` 的 scancode 方案已避開此問題;若你魔改成 pyautogui 會重新踩到此坑。
   - 中文辨識不準(建議改 large-v3 模型)
   - 轉錄太慢(建議改 small 模型)
   - 剪貼簿被污染(開啟 preserve_clipboard;注意僅保留純文字,圖片/檔案/富文本格式會遺失)
7. 授權(建議 MIT)

---

## 開發優先順序(建議階段式完成)

**Phase 1: MVP(先跑起來)**
- config.py + main.py 骨架
- recorder.py + transcriber.py + text_injector.py
- hotkey_manager.py(預設綁定 right ctrl)
- 能按住右 Ctrl → 說話 → 放開 → 貼字即可

**Phase 2: 完善基本功能**
- OpenCC 繁體轉換
- 保留使用者剪貼簿
- 處理各種錯誤情境
- setup.bat / run.bat

**Phase 3: 進階功能**
- 系統匣
- 轉錄歷史
- 支援自訂熱鍵(讓使用者可改成 Caps Lock 等其他鍵,並處理特殊鍵的預設行為)

**Phase 4: 打磨**
- PyInstaller 打包成 .exe(可選)
- 寫 README
- 加入單元測試

**未來考慮(暫不實作)**
- Ollama 本機 LLM 潤飾 — 使用者確認暫緩,等核心功能穩定再評估是否加入

---

## 給 Claude Code 的實作建議

1. **先從 Phase 1 開始**,跑起來之後再加功能,不要一次寫完全部
2. **大量使用 print/log**,讓使用者知道程式在做什麼,特別是第一次載入模型那段(會卡住幾秒)
3. **所有 I/O 動作都要 try/except**,特別是音訊、剪貼簿、網路
4. **中文註解**即可,使用者是中文母語者
5. **AI 潤飾(Ollama)第一版不實作**,config.json 雖有保留欄位,但實作上可忽略,等未來再加
6. **設定檔第一次不存在時要自動建立**,並在終端機提示使用者
7. **測試時請假設使用者是 Windows 11 + Python 3.11 + 沒有 GPU**,這是最常見的情境
8. **熱鍵綁定**:預設 `right ctrl`。使用 `keyboard.on_press_key("right ctrl", ...)` 綁定。**絕對不要用籠統的 `"ctrl"`**,否則會同時綁左右 Ctrl,干擾所有 Ctrl 快捷鍵。若綁定失敗,清楚告訴使用者並退回預設,不要讓程式崩潰。
9. **路徑處理**:一律用 `pathlib.Path` 與 `__file__` 相對路徑,避免使用者從別的資料夾執行時路徑錯亂

---

## 測試用的快速驗證流程

完成 Phase 1 後,使用者應該能做這件事:

1. `setup.bat`(一次)
2. `run.bat`
3. 打開記事本,游標點在裡面
4. 按住鍵盤右下角的**右 Ctrl**
5. 說「你好,今天天氣真不錯」
6. 放開右 Ctrl
7. 記事本應自動出現「你好,今天天氣真不錯。」

若此流程成功,Phase 1 即完成。
