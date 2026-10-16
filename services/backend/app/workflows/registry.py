import json
from copy import deepcopy
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from app.workflows.exceptions import UnknownWorkflow
from app.workflows.policies import ImageParameters, VideoParameters


@dataclass(frozen=True)
class WorkflowTemplate:
    name: str
    version: str
    workflow: dict[str, Any]


class WorkflowRegistry:
    _FILES = {
        ("z_image_turbo", "v1"): "z_image_turbo_v1.json",
        ("wan_i2v", "v1"): "wan_i2v_v1.json",
    }

    def __init__(self) -> None:
        self._templates: dict[tuple[str, str], WorkflowTemplate] = {}

    def get(self, name: str, version: str) -> WorkflowTemplate:
        key = (name, version)
        if key not in self._FILES:
            raise UnknownWorkflow(f"未审核的工作流：{name}:{version}")
        if key not in self._templates:
            path = files("app.workflows.templates").joinpath(self._FILES[key])
            self._templates[key] = WorkflowTemplate(name, version, json.loads(path.read_text(encoding="utf-8")))
        return self._templates[key]

    def render_image_workflow(self, parameters: ImageParameters) -> dict[str, Any]:
        workflow = deepcopy(self.get("z_image_turbo", "v1").workflow)
        workflow["4"]["inputs"]["text"] = parameters.prompt
        workflow["6"]["inputs"].update(
            width=parameters.width,
            height=parameters.height,
            batch_size=parameters.batch_size,
        )
        workflow["8"]["inputs"].update(seed=parameters.seed, steps=parameters.steps)
        return workflow

    def render_video_workflow(
        self,
        parameters: VideoParameters,
        uploaded_image_name: str,
    ) -> dict[str, Any]:
        workflow = deepcopy(self.get("wan_i2v", "v1").workflow)
        workflow["6"]["inputs"]["image"] = uploaded_image_name
        workflow["8"]["inputs"]["text"] = parameters.prompt
        workflow["9"]["inputs"]["text"] = parameters.negative_prompt
        workflow["10"]["inputs"].update(
            camera_pose=parameters.camera_pose,
            width=parameters.width,
            height=parameters.height,
            length=parameters.frames,
            speed=parameters.camera_speed,
        )
        workflow["12"]["inputs"].update(seed=parameters.seed, steps=parameters.steps)
        workflow["14"]["inputs"]["fps"] = parameters.fps
        return workflow
