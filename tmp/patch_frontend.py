"""Replace alert() calls with retry buttons in the frontend."""
import re

with open('static/index.html') as f:
    c = f.read()

# 1. Upload failed: replace alert with retry button
old = "alert('Upload failed: '+e.message);this.mainClear()"
new = "$('uploadStatus').innerHTML='<span style=\"color:#dc2626\">Upload failed</span><br><button class=\"btn btn-primary btn-xs\" onclick=\"A.upload(document.querySelector(\"input[type=file]\"))\">Retry</button>'"
c = c.replace(old, new)

# 2. Parse failed alert -> error message + reload
old = "alert('Parse failed: '+s.message);this.mainClear()"
new = "$('uploadStatus').innerHTML='<span style=\"color:#dc2626\">Parse failed: '+s.message+'</span><br><button class=\"btn btn-primary btn-xs\" onclick=\"location.reload()\">Reload</button>'"
c = c.replace(old, new)

# 3. Upload timeout alert -> retry button
old = "alert('Upload timed out after 30 min');this.mainClear()"
new = "$('uploadStatus').innerHTML='<span style=\"color:#dc2626\">Upload timed out</span><br><button class=\"btn btn-primary btn-xs\" onclick=\"location.reload()\">Reload</button>'"
c = c.replace(old, new)

with open('static/index.html', 'w') as f:
    f.write(c)

# Verify
s = c.rfind('<script>') + 8
e = c.rfind('</script>')
js = c[s:e]
print(f'Balanced: {js.count(chr(123)) == js.count(chr(125))}')
print(f'Alert remaining: {c.count("alert(")}')
