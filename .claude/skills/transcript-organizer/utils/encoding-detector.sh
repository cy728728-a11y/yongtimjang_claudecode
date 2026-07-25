#!/bin/bash
# encoding-detector.sh
# 파일 인코딩을 감지하고 필요시 UTF-8로 변환

FILE_PATH="$1"

if [ -z "$FILE_PATH" ]; then
    echo "Usage: $0 <file_path>"
    exit 1
fi

if [ ! -f "$FILE_PATH" ]; then
    echo "Error: File not found: $FILE_PATH"
    exit 1
fi

# 파일 인코딩 감지
ENCODING=$(file -I "$FILE_PATH" | grep -oP 'charset=\K[^ ]+')

echo "Detected encoding: $ENCODING"

# UTF-16 계열이면 UTF-8로 변환
if [[ "$ENCODING" == *"utf-16"* ]] || [[ "$ENCODING" == *"UTF-16"* ]]; then
    echo "Converting UTF-16 to UTF-8..."
    TEMP_FILE="/tmp/$(basename "$FILE_PATH" .txt)-utf8.txt"

    if iconv -f UTF-16 -t UTF-8 "$FILE_PATH" > "$TEMP_FILE" 2>/dev/null; then
        echo "✅ Converted successfully: $TEMP_FILE"
        echo "$TEMP_FILE"
    else
        echo "❌ Conversion failed. Trying with UTF-16LE..."
        if iconv -f UTF-16LE -t UTF-8 "$FILE_PATH" > "$TEMP_FILE" 2>/dev/null; then
            echo "✅ Converted successfully (UTF-16LE): $TEMP_FILE"
            echo "$TEMP_FILE"
        else
            echo "❌ Conversion failed. Trying with UTF-16BE..."
            if iconv -f UTF-16BE -t UTF-8 "$FILE_PATH" > "$TEMP_FILE" 2>/dev/null; then
                echo "✅ Converted successfully (UTF-16BE): $TEMP_FILE"
                echo "$TEMP_FILE"
            else
                echo "❌ All conversion attempts failed."
                exit 1
            fi
        fi
    fi
elif [[ "$ENCODING" == *"euc-kr"* ]] || [[ "$ENCODING" == *"EUC-KR"* ]]; then
    echo "Converting EUC-KR to UTF-8..."
    TEMP_FILE="/tmp/$(basename "$FILE_PATH" .txt)-utf8.txt"

    if iconv -f EUC-KR -t UTF-8 "$FILE_PATH" > "$TEMP_FILE" 2>/dev/null; then
        echo "✅ Converted successfully: $TEMP_FILE"
        echo "$TEMP_FILE"
    else
        echo "❌ EUC-KR conversion failed."
        exit 1
    fi
else
    # 이미 UTF-8이거나 다른 인코딩
    echo "File is already UTF-8 or compatible: $FILE_PATH"
    echo "$FILE_PATH"
fi
