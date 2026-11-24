"""Project 6: write your own binary encodings, then evolve the schema without breaking old or new code.

The record from Chapter 4:  {"userName": "Martin", "favoriteNumber": 1337, "interests": ["daydreaming", "hacking"]}

1. JSON: text, field names repeated in every record.
2. A Protocol Buffers-style encoding: each field is a TAG (field number + wire type) then the value.
   Integers are VARINTS (small numbers take fewer bytes). Unknown tags can be SKIPPED by their wire type.
3. An Avro-style encoding: no tags at all, just the values in schema order. The reader needs the WRITER'S schema,
   and resolves it against its own schema by field NAME.
4. Evolution: old code reads new data (forward compatibility) and new code reads old data (backward compatibility).

Run:  python p06_encoding.py
"""
import json

RECORD = {"userName": "Martin", "favoriteNumber": 1337, "interests": ["daydreaming", "hacking"]}


# ---------------- varints ----------------
def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def read_varint(buf: bytes, pos: int):
    shift = result = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def zigzag(n: int) -> int:                 # Avro: signed numbers, so -1 is small too
    return (n << 1) ^ (n >> 63)


def unzigzag(n: int) -> int:
    return (n >> 1) ^ -(n & 1)


# ---------------- Protocol Buffers style ----------------
# schema v1: field number -> (name, type). Wire types: 0 = varint, 2 = length-delimited.
PB_V1 = {1: ("userName", "string"), 2: ("favoriteNumber", "int"), 3: ("interests", "repeated string")}
# schema v2 adds field 4. Old fields keep their numbers forever.
PB_V2 = {**PB_V1, 4: ("photoUrl", "string")}


def pb_encode(record: dict, schema: dict) -> bytes:
    out = bytearray()
    for num, (name, typ) in schema.items():
        if name not in record:
            continue                       # optional: simply absent
        values = record[name] if typ.startswith("repeated") else [record[name]]
        for v in values:
            if typ == "int":
                out += varint(num << 3 | 0) + varint(v)
            else:
                data = v.encode()
                out += varint(num << 3 | 2) + varint(len(data)) + data
    return bytes(out)


def pb_decode(buf: bytes, schema: dict) -> dict:
    record, pos, skipped = {}, 0, []
    while pos < len(buf):
        key, pos = read_varint(buf, pos)
        num, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = read_varint(buf, pos)
        else:
            length, pos = read_varint(buf, pos)
            value, pos = buf[pos:pos + length], pos + length
        if num not in schema:
            skipped.append(num)            # a field from a newer schema: the wire type told us how long it is
            continue
        name, typ = schema[num]
        if typ != "int":
            value = value.decode()
        if typ.startswith("repeated"):
            record.setdefault(name, []).append(value)
        else:
            record[name] = value
    if skipped:
        record["(skipped unknown fields)"] = skipped
    return record


# ---------------- Avro style ----------------
NO_DEFAULT = object()
# (name, type, default). favoriteNumber is "null or long" with default null, as in the book's schema: one extra byte
# says which branch of the union follows.
AVRO_V1 = [("userName", "string", NO_DEFAULT), ("favoriteNumber", "union<null,long>", None),
           ("interests", "array<string>", [])]
# v2 removes favoriteNumber (allowed: it has a default) and adds photoUrl (allowed: it has a default).
AVRO_V2 = [("userName", "string", NO_DEFAULT), ("interests", "array<string>", []), ("photoUrl", "string", "")]
# v3 adds country WITHOUT a default: a mistake.
AVRO_V3 = AVRO_V2 + [("country", "string", NO_DEFAULT)]


def avro_encode(record: dict, schema: list) -> bytes:
    out = bytearray()
    for name, typ, default in schema:
        v = record.get(name, None if default is NO_DEFAULT else default)
        if typ == "union<null,long>":
            out += varint(zigzag(0)) if v is None else varint(zigzag(1)) + varint(zigzag(v))
        elif typ == "string":
            data = v.encode()
            out += varint(zigzag(len(data))) + data
        else:                              # array of strings: one block with a count, then 0
            if v:
                out += varint(zigzag(len(v)))
                for s in v:
                    data = s.encode()
                    out += varint(zigzag(len(data))) + data
            out += varint(0)
    return bytes(out)


def avro_decode(buf: bytes, writer: list, reader: list) -> dict:
    """Decode with the WRITER's schema (the only way to know what the bytes mean), then resolve to the READER's."""
    written, pos = {}, 0
    for name, typ, _ in writer:
        if typ == "union<null,long>":
            branch, pos = read_varint(buf, pos)
            if unzigzag(branch) == 0:
                written[name] = None
            else:
                n, pos = read_varint(buf, pos)
                written[name] = unzigzag(n)
        elif typ == "string":
            n, pos = read_varint(buf, pos)
            n = unzigzag(n)
            written[name], pos = buf[pos:pos + n].decode(), pos + n
        else:
            items = []
            while True:
                count, pos = read_varint(buf, pos)
                count = unzigzag(count)
                if count == 0:
                    break
                for _ in range(count):
                    n, pos = read_varint(buf, pos)
                    n = unzigzag(n)
                    items.append(buf[pos:pos + n].decode())
                    pos += n
            written[name] = items
    result = {}
    for name, typ, default in reader:      # match by NAME; missing in writer -> reader's default
        if name in written:
            result[name] = written[name]
        elif default is not NO_DEFAULT:
            result[name] = default
        else:
            raise ValueError(f"reader needs '{name}', the writer didn't write it, and there's no default")
    return result                          # fields only the writer had are simply ignored


if __name__ == "__main__":
    j = json.dumps(RECORD, separators=(",", ":")).encode()
    pb = pb_encode(RECORD, PB_V1)
    av = avro_encode(RECORD, AVRO_V1)
    print("1-3. The same record, three encodings:")
    print(f"   JSON                 {len(j):3d} bytes")
    print(f"   Protocol Buffers-ish {len(pb):3d} bytes  {pb.hex(' ')}")
    print(f"   Avro-ish             {len(av):3d} bytes  {av.hex(' ')}")
    print(f"   varint(1337) = {varint(1337).hex(' ')} (2 bytes instead of 8)")
    assert pb_decode(pb, PB_V1) == RECORD and avro_decode(av, AVRO_V1, AVRO_V1) == RECORD

    print("\n4. Schema evolution, Protocol Buffers style (tags)")
    new_record = {**RECORD, "photoUrl": "https://example.com/m.jpg"}
    new_bytes = pb_encode(new_record, PB_V2)
    print("   old code reads NEW data (forward):", pb_decode(new_bytes, PB_V1))
    print("   new code reads OLD data (backward):", pb_decode(pb, PB_V2), "-> photoUrl absent, use a default")
    renumbered = {1: ("userName", "string"), 3: ("favoriteNumber", "int"), 2: ("interests", "repeated string")}
    try:
        print("   if someone RENUMBERS fields:", pb_decode(pb, renumbered))
    except Exception as e:
        print(f"   if someone RENUMBERS fields: crash ({type(e).__name__}): never reuse or change a tag number")

    print("\n   Schema evolution, Avro style (writer's and reader's schemas)")
    v2_bytes = avro_encode({"userName": "Mona", "interests": ["chess"], "photoUrl": "m.jpg"}, AVRO_V2)
    print("   v2 reader, v1 data (backward):", avro_decode(av, AVRO_V1, AVRO_V2))
    print("   v1 reader, v2 data (forward): ", avro_decode(v2_bytes, AVRO_V2, AVRO_V1))
    try:
        avro_decode(av, AVRO_V1, AVRO_V3)
    except ValueError as e:
        print("   v3 reader, v1 data:", e)
    print("   Rule: you may only add or remove a field that has a default value.")
