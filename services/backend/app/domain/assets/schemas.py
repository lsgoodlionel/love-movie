from enum import StrEnum


class AssetKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    PREVIEW = "preview"
    SUBTITLE = "subtitle"
    AUDIO = "audio"
