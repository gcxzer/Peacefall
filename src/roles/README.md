# roles

`roles` 放角色、阵营和版型定义。

## 文件说明

- `types.py`：定义 `Camp`、`Role`，以及角色到阵营的映射。
- `role_sets.py`：定义可用版型，例如 `6p-classic`。

## 当前角色

- 狼人
- 平民
- 预言家
- 女巫

## 当前阵营

- 狼人阵营
- 好人阵营

## 新增角色或版型

新增角色时，先在 `types.py` 增加 `Role`，并确认 `role_camp` 能返回正确阵营。

新增版型时，在 `role_sets.py` 增加新的 `RoleSet`，再到 `src/role_set_engines/` 新建对应版型引擎。
