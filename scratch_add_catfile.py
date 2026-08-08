import json

files = {
 'named_032.json': '가구인테리어_서재사무용가구_책장.xlsx',
 'named_039.json': '가구인테리어_수예_수예용품부자재.xlsx',
 'named_240.json': '생활건강_반려동물_소동물용품_조류용품.xlsx',
}
base = r'D:\python_work\data\product-name\runs\2-2\named\\'
prefiltered = r'D:\python_work\data\product-name\runs\2-2\prefiltered\\'

for f, cf in files.items():
    path = base + f
    with open(path, encoding='utf-8') as fh:
        d = json.load(fh)
    for p in d['products']:
        p['카테고리파일'] = prefiltered + cf
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
print('done')
