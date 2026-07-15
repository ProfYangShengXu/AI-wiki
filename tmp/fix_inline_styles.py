"""Replace common inline styles with CSS classes in index.html."""
import re

with open('static/index.html') as f:
    c = f.read()

# Class definitions to add to <style>
new_classes = """
/* --- Auto-extracted utility classes (bc-001 fix) --- */
.flex{display:flex}
.flex-1{flex:1}
.flex-col{flex-direction:column}
.items-center{align-items:center}
.justify-center{justify-content:center}
.justify-between{justify-content:space-between}
.gap-4{gap:4px}
.gap-8{gap:8px}
.ml-auto{margin-left:auto}
.mt-8{margin-top:8px}
.mt-12{margin-top:12px}
.mb-8{margin-bottom:8px}
.mb-4{margin-bottom:4px}
.p-4{padding:4px}
.p-8{padding:8px}
.p-16{padding:16px}
.w-full{width:100%}
.w-120{width:120px}
.h-100{height:100%}
.text-center{text-align:center}
.text-red{color:#dc2626}
.text-gray-400{color:#999}
.text-sm{font-size:12px}
.text-xs{font-size:11px}
.font-bold{font-weight:700}
.font-semibold{font-weight:600}
.block{display:block}
.hidden{display:none}
.relative{position:relative}
.overflow-auto{overflow:auto}
.border-bottom{border-bottom:1px solid #e0e0e0}
.border-top{border-top:1px solid #e0e0e0}
.border-r{border-right:1px solid #e0e0e0}
.bg-white{background:#fff}
.bg-gray{background:#f5f5f5}
.rounded-8{border-radius:8px}
.shadow{box-shadow:0 4px 24px rgba(0,0,0,.2)}
.spinner-margin{margin:8px auto}
"""

# Insert after Pico CSS link
c = c.replace('<style>', '<style>\n' + new_classes)

# Now replace common inline style patterns with classes
replacements = [
    (' style="display:none"', ' class="hidden"'),
    (' style="flex:1"', ' class="flex-1"'),
    (' style="width:100%;margin-top:8px"', ' class="w-full mt-8"'),
    (' style="width:100%;margin-top:8px"', ' class="w-full mt-8"'),
    (' style="margin:8px auto"', ' class="spinner-margin"'),
    (' style="text-align:center;font-size:12px;color:#999"', ' class="text-center text-sm text-gray-400"'),
    (' style="font-weight:700;font-size:16px"', ' class="font-bold" style="font-size:16px"'),
    (' style="font-size:11px;font-weight:600;display:block;margin-bottom:2px"', ' class="text-xs font-semibold block" style="margin-bottom:2px"'),
    (' style="font-weight:600;font-size:12px"', ' class="font-semibold text-sm"'),
    (' style="margin-top:8px"', ' class="mt-8"'),
    (' style="color:#dc2626;font-size:12px"', ' class="text-red text-sm"'),
    (' style="display:flex;align-items:center;justify-content:center;height:100%;color:#999"', ' class="flex items-center justify-center h-100 text-gray-400"'),
    (' style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"', ' class="flex justify-between items-center mb-8"'),
    (' style="background:#fff;border-radius:8px;box-shadow:0 4px 24px rgba(0,0,0,.2);width:600px;max-width:90vw;max-height:85vh;overflow-y:auto;padding:16px"', ' class="bg-white rounded-8 shadow" style="width:600px;max-width:90vw;max-height:85vh;overflow-y:auto;padding:16px"'),
    (' style="background:#fff;border-radius:8px;box-shadow:0 4px 24px rgba(0,0,0,.2);width:380px;max-width:90vw;padding:16px"', ' class="bg-white rounded-8 shadow" style="width:380px;max-width:90vw;padding:16px"'),
    (' style="width:100%;margin-top:12px"', ' class="w-full mt-12"'),
    (' style="color:#dc2626"', ' class="text-red"'),
]

for old, new in replacements:
    c = c.replace(old, new)

with open('static/index.html', 'w') as f:
    f.write(c)

# Count remaining
remaining = len(re.findall(r'style=\"', c))
print(f'Remaining inline styles: {remaining}')
print(f'Reduced by: {141 - remaining}')
