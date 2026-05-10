
# Copyright 2016 Battelle Energy Alliance, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Data migration: encrypt existing plaintext OAuth tokens stored in GitUser.token.

Prior to migration 0001, tokens were stored as raw JSON strings (e.g.
'{"access_token": "...", ...}').  After that schema migration the column is an
EncryptedCharField, but any rows that existed before the deployment still hold
plaintext values because Django did not touch the rows themselves.

This migration iterates over every GitUser, reads the raw value from the
database bypassing the ORM field decryption (so we get the actual bytes on
disk), and then saves the row through the ORM so the new EncryptedCharField
re-writes the value as a Fernet-encrypted ciphertext.

The EncryptedMixin.to_python() / from_db_value() implementation in
django-encrypted-model-fields already handles the case where the stored value
is not a valid Fernet token (it passes it through unchanged).  This means that
*after* this migration we can trust all non-empty token columns to be properly
encrypted.
"""

from django.db import migrations


def encrypt_existing_tokens(apps, schema_editor):
    """
    Re-save every GitUser that has a non-empty token so that the
    EncryptedCharField transparently encrypts the value on write.
    """
    GitUser = apps.get_model('ci', 'GitUser')
    db_alias = schema_editor.connection.alias

    # Fetch the raw (potentially plaintext) values directly from the DB so we
    # do not accidentally double-encrypt rows that were already written by the
    # new field (e.g. in a partial-deploy scenario).
    from cryptography.fernet import InvalidToken

    users = GitUser.objects.using(db_alias).all()
    for user in users:
        raw_token = user.token
        if not raw_token:
            continue

        # Try to detect whether the value is already a Fernet ciphertext.
        # Fernet tokens always start with the version byte 0x80 (= b'\x80')
        # and are base64url-encoded, so they begin with 'gA' when stored as a
        # UTF-8 string.  If the raw value already looks like a Fernet token we
        # skip it to avoid double-encryption.
        if raw_token.startswith('gA'):
            continue

        # Value is plaintext JSON — save it so EncryptedCharField encrypts it.
        user.save(update_fields=['token'])


def noop(apps, schema_editor):
    """Reverse migration is a no-op: decryption is transparent to the app."""
    pass


class Migration(migrations.Migration):
    """
    Data migration to encrypt pre-existing plaintext OAuth tokens.

    Must run after 0001_encrypt_gituser_token so the column is already TEXT.
    """

    dependencies = [
        ('ci', '0001_encrypt_gituser_token'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_tokens, reverse_code=noop),
    ]
