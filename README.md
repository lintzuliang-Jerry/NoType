# 語音聽寫工具

100% 本機、免費、注重隱私的 Windows 語音聽寫桌面工具。按住熱鍵說話,放開後文字自動貼到游標所在位置。

- **完全離線**:語音資料永不離開你的電腦
- **免費**:不需要 API Key、訂閱或帳號
- **中文優化**:Whisper 模型 + OpenCC 繁體轉換

---

## 系統需求

- Windows 10 / 11
- Python 3.10+
- 至少 4 GB RAM(Whisper medium 模型)
- 麥克風

---

## 安裝

```bat
REM 1. 下載或 clone 專案
REM 2. 在專案資料夾執行:
setup.bat
```

`setup.bat` 會自動建立虛擬環境(`.venv`)並安裝所有相依套件。**只需執行一次。**

---

## 使用方式

```bat
run.bat
```

**第一次啟動**會從 Hugging Face 下載 Whisper medium 模型(約 500 MB),需要幾分鐘,請耐心等候。之後啟動就很快。

啟動後程式會常駐系統匣(工作列右下角)。右鍵圖示可控制。

### 基本流程

1. 把游標移到想要輸入文字的地方(記事本、瀏覽器輸入框、任何文字欄位)
2. **按住右 Ctrl** 開始錄音(終端機會顯示「🎤 錄音中...」)
3. 說出你要輸入的內容
4. **放開右 Ctrl** 停止錄音,程式自動轉錄並貼上

### 熱鍵說明

| 動作 | 預設熱鍵 |
|---|---|
| 開始/停止錄音 | 右 Ctrl(按住說話,放開轉錄) |
| 結束程式 | 系統匣 → 離開 |

如需更改熱鍵,編輯 `config.json` 的 `"hotkey"` 欄位(見下方設定說明)。

---

## 設定說明(`config.json`)

首次啟動時自動建立。可用任何文字編輯器修改。

```json
{
  "hotkey": "right ctrl",
  "hotkey_mode": "hold",
  "whisper": {
    "model_size": "medium",
    "language": "zh",
    "device": "auto",
    "compute_type": "int8",
    "initial_prompt": "以下是一段正式的繁體中文。..."
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

### 各欄位說明

| 欄位 | 說明 | 常用值 |
|---|---|---|
| `hotkey` | 錄音熱鍵 | `"right ctrl"` `"caps lock"` `"f9"` `"right alt"` |
| `hotkey_mode` | `"hold"` 按住說話 / `"toggle"` 按一下開始再按停止 | `"hold"` |
| `whisper.model_size` | Whisper 模型大小,越大越準但越慢 | `"tiny"` `"base"` `"small"` `"medium"` `"large-v3"` |
| `whisper.language` | 辨識語言 | `"zh"` 中文, `"en"` 英文, `null` 自動偵測 |
| `whisper.device` | `"auto"` 自動選擇, `"cpu"` 強制 CPU, `"cuda"` 強制 GPU | `"auto"` |
| `whisper.compute_type` | 量化精度,int8 最省資源 | `"int8"` `"float16"` `"float32"` |
| `output.convert_to_traditional` | 是否用 OpenCC 轉繁體(Whisper 有時輸出簡體) | `true` |
| `output.opencc_mode` | OpenCC 轉換模式 | `"s2twp"` 簡→台灣繁體含慣用詞 |
| `output.preserve_clipboard` | 貼上後還原原剪貼簿內容 | `true` |
| `history.enabled` | 是否記錄轉錄歷史到 `history.jsonl` | `true` |
| `tray.enabled` | 是否顯示系統匣圖示 | `true` |

---

## 疑難排解

### 熱鍵沒反應

1. **確認程式正在執行**:終端機/系統匣圖示應該存在。
2. **熱鍵被其他軟體佔用**:最常見的是:
   - **VirtualBox**:預設 Host Key 是右 Ctrl。在 VirtualBox 設定改成其他鍵,或在 `config.json` 把本工具的 `hotkey` 改成 `f9`。
   - **FPS 遊戲**:可能也綁右 Ctrl。換熱鍵解決。
   - **某些中文輸入法**:右 Ctrl 在部分輸入法設定中有作用。換熱鍵或調整輸入法設定。
3. **目標視窗是以管理員身分執行的程式**(工作管理員、regedit、以 admin 啟動的程式):Windows 安全隔離會阻擋一般程式監聽這類視窗的鍵盤事件和貼字。解法:用滑鼠右鍵點 `run.bat` → 「以系統管理員身分執行」。

### 錄完沒貼上 / 貼出字元 v

通常是中文 IME 攔截了 Ctrl+V。本工具預設使用 `keyboard.send` 的 scancode 方案應已避免此問題。若仍發生,請回報 issue 並說明使用的輸入法名稱。

### 中文辨識不準

- 改用更大的模型:在 `config.json` 設定 `"model_size": "large-v3"`(需額外下載約 3 GB)。
- 確認 `initial_prompt` 有設定,引導模型輸出繁體中文。
- 錄音環境嘈雜時辨識率會下降。

### 轉錄太慢

- 改用較小模型:`"model_size": "small"` 或 `"base"`,速度快但準確度略降。
- 若有 NVIDIA GPU,確認 `"device": "auto"` 有正確偵測(啟動時終端機會顯示實際使用的裝置)。
- 啟動後終端機若顯示 `裝置=cpu`,但你有 GPU,可能是 CUDA runtime 版本不相符,嘗試更新 CUDA 或 cudnn。

### 剪貼簿被污染

確認 `config.json` 中 `"preserve_clipboard": true`。

**注意**:本工具使用 `pyperclip` 保留剪貼簿,**只能保留純文字**。若原本剪貼簿是圖片、檔案、或帶格式的文字,觸發一次聽寫後這些內容會遺失。這是已知限制。

### 啟動時出現 `pystray` / `Pillow` 相關錯誤

執行 `setup.bat` 重新安裝相依套件。若問題持續,刪除 `.venv` 資料夾後再執行 `setup.bat`。

### 無法找到麥克風

確認 Windows 音效設定中有預設錄音裝置,且麥克風沒有被其他應用程式獨占。

---

## 轉錄歷史

每次轉錄結果會自動存到 `history.jsonl`(JSON Lines 格式)。可用文字編輯器或 `jq` 等工具查閱。若不想保留記錄,在 `config.json` 設定 `"history": { "enabled": false }`。

---

## 授權

MIT License

---

## 常見設定範例

**換成 Caps Lock 當熱鍵(使用 toggle 模式)**
```json
{
  "hotkey": "caps lock",
  "hotkey_mode": "toggle"
}
```
> 程式會自動阻止 Caps Lock 切換大小寫狀態。

**追求最高準確度(有 GPU 或不介意慢)**
```json
{
  "whisper": {
    "model_size": "large-v3",
    "compute_type": "float16"
  }
}
```

**追求最快速度(舊電腦)**
```json
{
  "whisper": {
    "model_size": "small",
    "compute_type": "int8"
  }
}
```
