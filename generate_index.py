import os
import zipfile

# الامتدادات التي نريد قراءتها
extensions = (".py", ".txt", ".md", ".json", ".yml", ".yaml", ".html", ".css", ".js")

index_file = "project_index.txt"

# توليد الملف
with open(index_file, "w", encoding="utf-8") as outfile:
    for root, _, files in os.walk("."):
        for file in files:
            if file.endswith(extensions):
                path = os.path.join(root, file)
                if index_file in path:
                    continue
                outfile.write(f"\n\n# FILE: {path}\n")
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        outfile.write(f.read())
                except Exception as e:
                    outfile.write(f"\n[!!] Error reading file {path}: {e}\n")

# ضغط الملف الناتج
with zipfile.ZipFile("project_index.zip", "w", zipfile.ZIP_DEFLATED) as zipf:
    zipf.write(index_file)

print("[OK] تم إنشاء project_index.txt وضغطه داخل project_index.zip")
