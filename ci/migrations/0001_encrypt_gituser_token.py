
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

from django.db import migrations
import encrypted_model_fields.fields


class Migration(migrations.Migration):
    """
    Schema migration: change GitUser.token from a plain CharField to an
    EncryptedCharField.  EncryptedMixin.get_internal_type() returns "TextField"
    so the underlying DB column type changes from VARCHAR(1024) to TEXT, which
    is the only DDL change required.
    """

    dependencies = []

    operations = [
        migrations.AlterField(
            model_name='gituser',
            name='token',
            field=encrypted_model_fields.fields.EncryptedCharField(blank=True),
        ),
    ]
