"""Minimal 7z reader (LZMA / LZMA2 / BCJ x86 / copy), stdlib only."""
import lzma, struct, sys, os


class R:
    def __init__(s, b, p=0): s.b, s.p = b, p
    def byte(s): v = s.b[s.p]; s.p += 1; return v
    def bytes(s, n): v = s.b[s.p:s.p + n]; s.p += n; return v
    def num(s):
        first = s.byte(); mask = 0x80; val = 0
        for i in range(8):
            if first & mask == 0:
                hi = first & (mask - 1)
                return val | (hi << (8 * i))
            val |= s.byte() << (8 * i); mask >>= 1
        return val
    def bits(s, n):
        out, cur, m = [], 0, 0
        for _ in range(n):
            if m == 0: cur, m = s.byte(), 0x80
            out.append(bool(cur & m)); m >>= 1
        return out
    def defbits(s, n):
        allset = s.byte()
        return [True] * n if allset else s.bits(n)


def read_streams(r):
    info = {"packpos": 0, "packsizes": [], "folders": [], "unpack": [], "substreams": None}
    while True:
        t = r.byte()
        if t == 0: return info
        if t == 6:  # PackInfo
            info["packpos"] = r.num(); n = r.num()
            while True:
                k = r.byte()
                if k == 0: break
                if k == 9: info["packsizes"] = [r.num() for _ in range(n)]
                elif k == 10: d = r.defbits(n); [r.bytes(4) for x in d if x]
        elif t == 7:  # UnpackInfo
            assert r.byte() == 0x0B
            nf = r.num(); assert r.byte() == 0
            for _ in range(nf):
                coders = []
                for _ in range(r.num()):
                    f = r.byte(); cid = r.bytes(f & 0xF)
                    ni = no = 1
                    if f & 0x10: ni, no = r.num(), r.num()
                    props = r.bytes(r.num()) if f & 0x20 else b""
                    coders.append((cid, props, ni, no))
                tot_out = sum(c[3] for c in coders); tot_in = sum(c[2] for c in coders)
                bps = [(r.num(), r.num()) for _ in range(tot_out - 1)]
                npacked = tot_in - len(bps)
                packed = [r.num() for _ in range(npacked)] if npacked > 1 else [0]
                info["folders"].append({"coders": coders, "bps": bps, "packed": packed})
            assert r.byte() == 0x0C
            for fo in info["folders"]:
                fo["sizes"] = [r.num() for _ in range(sum(c[3] for c in fo["coders"]))]
            while True:
                k = r.byte()
                if k == 0: break
                if k == 10: d = r.defbits(nf); [r.bytes(4) for x in d if x]
        elif t == 8:  # SubStreamsInfo
            nums = [1] * len(info["folders"])
            sizes = []
            k = r.byte()
            if k == 0x0D: nums = [r.num() for _ in info["folders"]]; k = r.byte()
            if k == 9:
                for fi, n in enumerate(nums):
                    s = 0
                    for _ in range(n - 1):
                        v = r.num(); sizes.append(v); s += v
                    sizes.append(unpack_size(info["folders"][fi]) - s)
                k = r.byte()
            else:
                for fi, n in enumerate(nums):
                    if n == 1: sizes.append(unpack_size(info["folders"][fi]))
            while k != 0:
                if k == 10:
                    cnt = sum(nums); d = r.defbits(cnt); [r.bytes(4) for x in d if x]
                k = r.byte()
            info["substreams"] = (nums, sizes)


def unpack_size(fo):
    bound = {o for _, o in fo["bps"]}
    for i in range(len(fo["sizes"])):
        if i not in bound: return fo["sizes"][i]


def decode_folder(data, pos, packsize, fo):
    raw = data[pos:pos + packsize]
    filters = []
    for cid, props, ni, no in reversed(fo["coders"]) if len(fo["coders"]) > 1 else fo["coders"]:
        pass
    # coders listed outer->inner; decode chain = apply coders in order (first coder is final output)
    chain = []
    for cid, props, ni, no in fo["coders"]:
        if cid == b"\x03\x01\x01":
            d = props[0]; pb = d // 45; lp = (d % 45) // 9; lc = d % 9
            chain.append({"id": lzma.FILTER_LZMA1, "dict_size": struct.unpack("<I", props[1:5])[0], "lc": lc, "lp": lp, "pb": pb})
        elif cid == b"\x21":
            chain.append({"id": lzma.FILTER_LZMA2, "dict_size": 1 << 26})
        elif cid == b"\x03\x03\x01\x03":
            chain.append({"id": lzma.FILTER_X86})
        elif cid == b"\x03":
            chain.append({"id": lzma.FILTER_DELTA, "dist": props[0] + 1})
        elif cid == b"\x00":
            continue
        else:
            raise ValueError(f"unsupported coder {cid.hex()}")
    if not chain: return raw
    # lzma wants filters ordered BCJ first then LZMA (decoder applies in reverse)
    chain.sort(key=lambda f: 0 if f["id"] in (lzma.FILTER_X86, lzma.FILTER_DELTA) else 1)
    out = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=chain).decompress(raw, unpack_size(fo))
    return out[:unpack_size(fo)]


def read_names(b):
    return b.decode("utf-16-le").split("\x00")[:-1]


def open7z(path):
    data = open(path, "rb").read()
    off, size = struct.unpack("<QQ", data[12:28])
    r = R(data, 32 + off)
    t = r.byte()
    while t == 0x17:  # encoded header
        si = read_streams(r)
        pos = 32 + si["packpos"]
        hdr = decode_folder(data, pos, si["packsizes"][0], si["folders"][0])
        r = R(hdr); t = r.byte()
    assert t == 1
    main, files = None, []
    while True:
        k = r.byte()
        if k == 0: break
        if k == 4: main = read_streams(r)
        elif k == 5:
            nfiles = r.num(); empty = [False] * nfiles
            names = []; emptyfile = None; attrs = [None] * nfiles
            while True:
                pt = r.byte()
                if pt == 0: break
                sz = r.num(); body = R(r.bytes(sz))
                if pt == 0x0E: empty = body.bits(nfiles)
                elif pt == 0x11: body.byte(); names = read_names(body.b[1:])
                elif pt == 0x0F: emptyfile = body.bits(sum(empty))
                elif pt == 0x15:
                    d = body.defbits(nfiles); body.byte()
                    for i in range(nfiles):
                        if d[i]: attrs[i] = struct.unpack("<I", body.bytes(4))[0]
            ei = 0; kinds = []
            for i in range(nfiles):
                if not empty[i]: kinds.append("file"); continue
                isfile = emptyfile[ei] if emptyfile else False; ei += 1
                if attrs[i] is not None: isfile = not (attrs[i] & 0x10)
                kinds.append("emptyfile" if isfile else "dir")
            files = list(zip(names, kinds))
    return data, main, files


def extract(path, outdir):
    data, main, files = open7z(path)
    nums, sizes = main["substreams"] if main["substreams"] else ([1] * len(main["folders"]), [unpack_size(f) for f in main["folders"]])
    pos = 32 + main["packpos"]; pi = 0; si = 0
    blobs = []
    for fi, fo in enumerate(main["folders"]):
        npk = len(fo["packed"])
        out = decode_folder(data, pos, main["packsizes"][pi], fo)
        pos += sum(main["packsizes"][pi:pi + npk]); pi += npk
        o = 0
        for _ in range(nums[fi]):
            blobs.append(out[o:o + sizes[si]]); o += sizes[si]; si += 1
    bi = 0
    for name, isempty in files:
        p = os.path.join(outdir, name.replace("\\", "/"))
        if isempty == "dir":
            os.makedirs(p, exist_ok=True); continue
        if isempty == "emptyfile":
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True); open(p, "wb").close(); continue
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        open(p, "wb").write(blobs[bi]); bi += 1
    return [n for n, _ in files]


if __name__ == "__main__":
    for n in extract(sys.argv[1], sys.argv[2]): print(n)
