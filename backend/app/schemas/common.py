from typing import Annotated

from pydantic import StringConstraints

DeviceId = Annotated[str, StringConstraints(pattern=r"^DEVICE-(CHEST|WAIST|THIGH|OTHER)-\d{3}$")]
SessionId = Annotated[str, StringConstraints(pattern=r"^\d{8}_\d{6}_[A-F0-9]{8}$")]
AnnotationId = Annotated[str, StringConstraints(pattern=r"^ANN-\d{8}_\d{6}_[A-F0-9]{8}-\d{4}$")]
DeviceRole = Annotated[str, StringConstraints(pattern=r"^(chest|waist|thigh|other)$")]
LabelName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(\.[a-z0-9_]+){2,}$")]
