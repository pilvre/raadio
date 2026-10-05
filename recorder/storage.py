"""Salvestuskiht: Cloudflare R2 (S3 API) või kohalik kaust – sama liides.

Võtmed on kujul "rec/....mp3", "live/....json", "config.json" jne.
"""

import json
import os
import shutil
import tempfile
import time
from pathlib import Path


class R2Storage:
    kind = "r2"

    def __init__(self, env):
        import boto3
        from botocore.config import Config

        self.bucket = env.get("R2_BUCKET", "kuku")
        self.s3 = boto3.client(
            "s3",
            endpoint_url=env["R2_ENDPOINT"],
            aws_access_key_id=env["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
            config=Config(retries={"max_attempts": 5}),
        )

    def get_json(self, key, default=None):
        try:
            return json.loads(self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read())
        except self.s3.exceptions.NoSuchKey:
            return default

    def put_json(self, key, data):
        self.s3.put_object(Bucket=self.bucket, Key=key, ContentType="application/json",
                           Body=json.dumps(data, ensure_ascii=False, indent=1).encode())

    def put_file(self, path, key, content_type="audio/mpeg"):
        self.s3.upload_file(str(path), self.bucket, key, ExtraArgs={"ContentType": content_type})

    def get_file(self, key, path):
        self.s3.download_file(self.bucket, key, str(path))

    def list(self, prefix):
        """-> [(key, size)]"""
        out, token = [], None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                kw["ContinuationToken"] = token
            page = self.s3.list_objects_v2(**kw)
            out += [(o["Key"], o["Size"]) for o in page.get("Contents", [])]
            if not page.get("IsTruncated"):
                return out
            token = page["NextContinuationToken"]

    def exists(self, key):
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def copy(self, src, dst, content_type="audio/mpeg"):
        self.s3.copy_object(Bucket=self.bucket, Key=dst, ContentType=content_type, MetadataDirective="REPLACE",
                            CopySource={"Bucket": self.bucket, "Key": src})

    def delete(self, keys):
        if keys:
            self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": [{"Key": k} for k in keys]})


class LocalStorage:
    kind = "local"

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key):
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise ValueError(f"vigane võti: {key}")
        return p

    def _atomic_write(self, key, write):
        dest = self.path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                write(f)
            # Windows ei luba asendada faili, mida keegi parasjagu loeb (nt pleier) -> proovi uuesti
            for attempt in range(20):
                try:
                    os.replace(tmp, dest)
                    break
                except PermissionError:
                    if attempt == 19:
                        raise
                    time.sleep(0.25)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def get_json(self, key, default=None):
        try:
            return json.loads(self.path(key).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def put_json(self, key, data):
        body = json.dumps(data, ensure_ascii=False, indent=1).encode()
        self._atomic_write(key, lambda f: f.write(body))

    def put_file(self, path, key, content_type=None):
        def write(f):
            with open(path, "rb") as src:
                shutil.copyfileobj(src, f)
        self._atomic_write(key, write)

    def get_file(self, key, path):
        shutil.copyfile(self.path(key), path)

    def list(self, prefix):
        base = self.path(prefix.rstrip("/")) if prefix else self.root
        if not base.exists():
            return []
        return [(str(p.relative_to(self.root)), p.stat().st_size)
                for p in sorted(base.rglob("*")) if p.is_file() and not p.name.startswith(".")]

    def exists(self, key):
        return self.path(key).is_file()

    def copy(self, src, dst, content_type=None):
        self.put_file(self.path(src), dst)

    def delete(self, keys):
        for k in keys:
            for attempt in range(20):
                try:
                    self.path(k).unlink(missing_ok=True)
                    break
                except PermissionError:  # Windows: fail lahti
                    if attempt == 19:
                        raise
                    time.sleep(0.25)


def make_storage(env):
    mode = (env.get("STORAGE") or ("r2" if env.get("R2_SECRET_ACCESS_KEY") else "local")).lower()
    if mode == "r2":
        return R2Storage(env)
    return LocalStorage(env.get("LOCAL_DIR") or "~/Music/Raadiosalvestaja")
