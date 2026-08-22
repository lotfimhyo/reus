"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

طبقة العنقود (Cluster Layer) — ما تبقى هنا بعد تنظيف هذه الحلقة هو فعليًا
كل ما هو **حيّ**: مكوّنات تُستخدَم فعليًا من `infrastructure/node_runtime.py`
(التركيب الإنتاجي الحقيقي الوحيد لعقدة، انظر توثيقه) أو من مكوّنات تلك
المكوّنات نفسها.

ملاحظة تاريخية (للسياق، لا كتحذير حالي): كانت هذه الحزمة تحتوي سابقًا آلية
انضمام أقدم قائمة على "سر عنقود" (HMAC cluster-secret) مع اكتشاف UDP، من
مرحلة "Veritas AI" الأولى للمشروع. تلك الآلية استُبدلت بآلية mTLS +
موافقة بشرية عبر تلغرام (`MTLSJoinClient`، `SecureRemoteExecutor`، في
ملفيهما مباشرة — انظر ملاحظة الاستيراد أدناه) في حلقة تطوير سابقة — القرار
المعماري نفسه (اعتماد mTLS كآلية الثقة الوحيدة) اتُّخذ ونُفِّذ فعليًا حينها؛
ما تبقى غير منجَز كان فقط حذف الكود القديم غير المُستخدَم بعد الاستبدال.
تحقَّق هذا التنظيف بثلاث عمليات بحث مستقلة عبر كل المستودع (بما في ذلك كل
الاختبارات) قبل الحذف: لا شيء خارج هذه الحزمة نفسها كان يستورد أيًا من
الملفات المحذوفة (cluster_secret.py، discovery.py [نسخة UDP]، join_client.py،
join_protocol.py، node.py، node_identity.py، remote_executor.py،
cluster_executor.py) — كانت جميعها تشير لبعضها فقط، كتلة معزولة تمامًا عن
أي مسار تنفيذ حقيقي.

ملاحظة استيراد مقصودة: `MTLSJoinClient` و`SecureRemoteExecutor` **لا**
يُعاد تصديرهما من هنا عمدًا (رغم كونهما الاستخدام الحي الفعلي لهذه الحزمة)
— استوردهما مباشرة من ملفيهما
(`infrastructure.cognitive_core.cluster.mtls_join_client` /
`.secure_remote_executor`)، كما يفعل `node_runtime.py` وكل مستدعٍ حقيقي
آخر فعلًا. تصديرهما هنا يُنشئ استيرادًا دائريًا حقيقيًا مع
`infrastructure.cluster_network.cluster_snapshot_node` (يُعاد إنتاجه
بالتجربة الفعلية: ذلك الملف يستورد `peer_directory` من هذه الحزمة، ما
يُشغِّل `__init__.py` هذا أثناء تحميله هو نفسه لم يكتمل بعد؛ لو استورد
`__init__.py` بدوره mtls_join_client الذي يستورد رجوعًا من
cluster_snapshot_node، ينهار الاستيراد). الإبقاء على الاستيراد المباشر
بالملف (كما هو متّبع فعليًا في كل الكود الحي) يتفادى هذا تمامًا.
"""

from infrastructure.cognitive_core.cluster.exceptions import (
    ClusterConnectionError,
    ClusterJoinRejectedError,
    VeritasClusterError,
)
from infrastructure.cognitive_core.cluster.peer_directory import PeerDirectory

__all__ = [
    "PeerDirectory",
    "VeritasClusterError",
    "ClusterConnectionError",
    "ClusterJoinRejectedError",
]
