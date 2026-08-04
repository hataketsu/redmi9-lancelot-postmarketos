#!/usr/bin/env python3
"""Chuyen <part>.new.dat + <part>.transfer.list cua Android OTA thanh raw ext4 image."""
import sys

def main(transfer_list, new_data, out_img):
    with open(transfer_list) as f:
        lines = f.read().splitlines()
    version = int(lines[0])
    # lines[1] = tong so block; v>=2 co them 2 dong stash
    cmds_start = 4 if version >= 2 else 2

    max_block = 0
    cmds = []
    for line in lines[cmds_start:]:
        if not line.strip():
            continue
        op, _, rest = line.partition(' ')
        if op != 'new':
            continue
        nums = [int(x) for x in rest.split(',')]
        # nums[0] = so luong phan tu con lai, sau do la cac cap [begin, end)
        pairs = nums[1:]
        for i in range(0, len(pairs), 2):
            b, e = pairs[i], pairs[i+1]
            cmds.append((b, e))
            max_block = max(max_block, e)

    print(f'version={version}  so doan new={len(cmds)}  block cao nhat={max_block}')
    BS = 4096
    with open(new_data, 'rb') as src, open(out_img, 'wb') as dst:
        dst.truncate(max_block * BS)
        for b, e in cmds:
            dst.seek(b * BS)
            remaining = (e - b) * BS
            while remaining:
                chunk = src.read(min(remaining, 8 << 20))
                if not chunk:
                    raise SystemExit(f'.dat het du lieu som tai block {b}')
                dst.write(chunk)
                remaining -= len(chunk)
    print('xong ->', out_img)

if __name__ == '__main__':
    main(*sys.argv[1:4])
