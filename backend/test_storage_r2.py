"""Private R2 smoke: upload, read, reject an unsigned read, then delete only this object."""
import base64,secrets
from image_storage import MODE,R2_BUCKET,put_image,get_image,delete_image,unsigned_read_denied,StorageError
if MODE!='r2':raise SystemExit('R2 storage configuration required')
raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=')
name=secrets.token_hex(16)+'.png'
created=False
try:
    put_image(name,raw,'image/png');created=True
    assert get_image(name)==raw
    assert unsigned_read_denied(name)
    print('PASS: private R2 bucket',R2_BUCKET,'upload/download match; unsigned read denied')
finally:
    if created:
        delete_image(name)
        try:get_image(name);raise SystemExit('Smoke object was still readable after delete')
        except (FileNotFoundError,StorageError) as exc:
            if isinstance(exc,StorageError) and exc.status!=404:raise
        print('Only the unique smoke-test object was removed')
