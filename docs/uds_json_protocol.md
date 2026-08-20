# UDS JSON 协议说明

本文档基于 [src/unitelabs/usila_c/socket_client.py](../src/unitelabs/usila_c/socket_client.py) 与各功能模块的调用代码整理，说明当前项目中通过 Unix Domain Socket（UDS）实际发送和接收的 JSON 结构。

## 1. 发送格式

所有命令都走统一的 `send_request` 入口，发送内容为：

```json
{
  "cmd": "FeatureName.CommandName",
  "params": {
    "key": "value"
  },
  "req_id": "uuid-string"
}
```

对应实现来自 `UdsClient.send_request()`：

```python
payload = json.dumps({"cmd": cmd, "params": params, "req_id": req_id}) + "\n"
self.writer.write(payload.encode("utf-8"))
```

### 1.1 字段说明

- `cmd`: 命令名，格式为 `模块名.方法名`，如 `DeviceBase.Initialize`，`LID.Aspirate`
- `params`: 命令参数对象，按具体功能不同而变化
- `req_id`: 每次请求生成的 UUID，用于匹配请求与响应

> 发送时会在 JSON 后追加一个换行符 `\n`，服务端通常按行读取一条 JSON。

---

## 2. 接收格式

服务端返回的 JSON 也是按一行读取，结构大致为：

```json
{
  "req_id": "uuid-string",
  "code": 0,
  "msg": "success",
  "result": {
    "key": "value"
  }
}
```

### 2.1 字段说明

- `req_id`: 与请求中的 `req_id` 一致，用于校验对应关系
- `code`: 执行状态码，`0` 表示成功，非 `0` 表示失败
- `msg`: 失败或成功说明文字
- `result`: 具体返回数据，通常为键值对象

客户端会检查：

```python
if resp["req_id"] != req_id:
    raise RuntimeError(...)
```

因此 `req_id` 是必须字段，且必须一一对应。

---

## 3. 通用数据结构

以下对象在多个功能模块中被反复使用。

### 3.1 3D 坐标

`Position3D` 在多个命令中传递逻辑坐标：

```json
{
  "x": 12.5,
  "y": 34.0,
  "z": 56.7
}
```

对应 Python 结构：

```python
{"x": position.x, "y": position.y, "z": position.z}
```

### 3.2 夹爪参数

`GripperParam`：

```json
{
  "position": 15.0,
  "force": 12.5
}
```

### 3.3 电机位置

`MotorPosition3D`：

```json
{
  "mx": 1000.0,
  "my": 2000.0,
  "mz": 3000.0
}
```

### 3.4 标定点对

`CalibrationPair`：

```json
{
  "logical_pos": {
    "x": 10.0,
    "y": 20.0,
    "z": 30.0
  },
  "motor_pos": {
    "mx": 1000.0,
    "my": 2000.0,
    "mz": 3000.0
  }
}
```

---

## 4. 各功能模块命令格式

### 4.1 DeviceBase

#### `DeviceBase.Initialize`

请求：

```json
{
  "cmd": "DeviceBase.Initialize",
  "params": {},
  "req_id": "..."
}
```

成功返回：

```json
{
  "req_id": "...",
  "code": 0,
  "msg": "success",
  "result": {}
}
```

#### `DeviceBase.EmergencyStop`

```json
{
  "cmd": "DeviceBase.EmergencyStop",
  "params": {},
  "req_id": "..."
}
```

#### `DeviceBase.SetGeneralParameters`

```json
{
  "cmd": "DeviceBase.SetGeneralParameters",
  "params": {
    "x_speed": 100.0,
    "y_speed": 120.0,
    "powder_z_speed": 80.0,
    "gripper_z_speed": 90.0,
    "liquid_z_speed": 95.0,
    "gripper_speed": 110.0
  },
  "req_id": "..."
}
```

#### `DeviceBase.CoordinateCalibration`

```json
{
  "cmd": "DeviceBase.CoordinateCalibration",
  "params": {
    "powder_z_calibration": [
      {
        "logical_pos": {"x": 0, "y": 0, "z": 0},
        "motor_pos": {"mx": 0, "my": 0, "mz": 0}
      }
    ],
    "gripper_z_calibration": [
      {
        "logical_pos": {"x": 0, "y": 0, "z": 0},
        "motor_pos": {"mx": 0, "my": 0, "mz": 0}
      }
    ],
    "liquid_z_calibration": [
      {
        "logical_pos": {"x": 0, "y": 0, "z": 0},
        "motor_pos": {"mx": 0, "my": 0, "mz": 0}
      }
    ]
  },
  "req_id": "..."
}
```

典型返回：

```json
{
  "req_id": "...",
  "code": 0,
  "msg": "success",
  "result": {
    "powder_z_residual": "0.01",
    "gripper_z_residual": "0.02",
    "liquid_z_residual": "0.03",
    "calibration_timestamp": "2026-08-18T00:00:00Z"
  }
}
```

#### 设备状态查询

查询命令的请求通常是空参数：

```json
{
  "cmd": "DeviceBase.GetDeviceState",
  "params": {},
  "req_id": "..."
}
```

返回示例：

```json
{
  "req_id": "...",
  "code": 0,
  "msg": "success",
  "result": {
    "status": 1
  }
}
```

对应代码中会读取：

```python
resp["result"]["status"]
```

`DeviceBase` 还会通过以下可观察属性轮询设备状态。它们的请求均使用空参数，返回值从 `result` 中读取：

| 属性 | 请求命令 | 返回字段 | 类型 |
| --- | --- | --- | --- |
| `DeviceState` | `DeviceBase.GetDeviceState` | `status` | `int` |
| `FaultReason` | `DeviceBase.GetFaultReason` | `fault_reason` | `str` |
| `XPosition` | `DeviceBase.GetXPos` | `logic` | `float` |
| `XMotorPosition` | `DeviceBase.GetXPos` | `motor` | `float` |
| `YPosition` | `DeviceBase.GetYPos` | `logic` | `float` |
| `YMotorPosition` | `DeviceBase.GetYPos` | `motor` | `float` |
| `PowderZPosition` | `DeviceBase.GetPowderZPos` | `logic` | `float` |
| `PowderZMotorPosition` | `DeviceBase.GetPowderZPos` | `motor` | `float` |
| `GripperZPosition` | `DeviceBase.GetGripperZPos` | `logic` | `float` |
| `GripperZMotorPosition` | `DeviceBase.GetGripperZPos` | `motor` | `float` |
| `LiquidZPosition` | `DeviceBase.GetLiquidZPos` | `logic` | `float` |
| `LiquidZMotorPosition` | `DeviceBase.GetLiquidZPos` | `motor` | `float` |
| `GripperForce` | `DeviceBase.GetGripperState` | `force` | `float` |
| `GripperPosition` | `DeviceBase.GetGripperState` | `position` | `float` |

例如，获取夹爪状态的请求和返回如下：

```json
{
  "cmd": "DeviceBase.GetGripperState",
  "params": {},
  "req_id": "..."
}
```

```json
{
  "req_id": "...",
  "code": 0,
  "msg": "success",
  "result": {
    "force": 12.5,
    "position": 15.0
  }
}
```

---

### 4.2 WS（天平）

#### `WS.Tare`

```json
{
  "cmd": "WS.Tare",
  "params": {},
  "req_id": "..."
}
```

#### `WS.GetGrossWeight`

```json
{
  "cmd": "WS.GetGrossWeight",
  "params": {},
  "req_id": "..."
}
```

返回示例：

```json
{
  "req_id": "...",
  "code": 0,
  "msg": "success",
  "result": {
    "weight_g": 123.45
  }
}
```

---

### 4.3 CAP

#### `CAP.OpenCap`

```json
{
  "cmd": "CAP.OpenCap",
  "params": {
    "container_diameter": 80.0,
    "open_position": {"x": 10.0, "y": 20.0, "z": 30.0},
    "cap_place_position": {"x": 40.0, "y": 50.0, "z": 60.0},
    "open_gripper_param": {"position": 15.0, "force": 12.5},
    "close_gripper_param": {"position": 10.0, "force": 10.0},
    "rotation_cycles": 2,
    "rotation_speed": 30.0,
    "rotation_force": 5.0,
    "z_lift_height": 8.0
  },
  "req_id": "..."
}
```

#### `CAP.CloseCap`

```json
{
  "cmd": "CAP.CloseCap",
  "params": {
    "close_position": {"x": 10.0, "y": 20.0, "z": 30.0},
    "rotation_cycles": 2,
    "rotation_speed": 30.0,
    "rotation_force": 5.0,
    "z_lift_height": 8.0
  },
  "req_id": "..."
}
```

---

### 4.4 LID（移液器）

#### `LID.AttachTip`

```json
{
  "cmd": "LID.AttachTip",
  "params": {
    "tip_position": {"x": 10.0, "y": 20.0, "z": 30.0},
    "press_force": 12.5
  },
  "req_id": "..."
}
```

#### `LID.Aspirate`

```json
{
  "cmd": "LID.Aspirate",
  "params": {
    "target_position": {"x": 10.0, "y": 20.0, "z": 30.0},
    "volume": 150.0,
    "aspirate_speed": 200.0,
    "immersion_depth": 2.0
  },
  "req_id": "..."
}
```

#### `LID.Dispense`

```json
{
  "cmd": "LID.Dispense",
  "params": {
    "target_position": {"x": 10.0, "y": 20.0, "z": 30.0},
    "volume": 150.0,
    "dispense_speed": 200.0,
    "immersion_depth": 2.0
  },
  "req_id": "..."
}
```

#### `LID.EjectTip`

```json
{
  "cmd": "LID.EjectTip",
  "params": {
    "eject_position": {"x": 10.0, "y": 20.0, "z": 30.0},
    "eject_force": 12.5
  },
  "req_id": "..."
}
```

---

### 4.5 FFQ（粉体处理）

#### `FFQ.LoadPowderBucket`

```json
{
  "cmd": "FFQ.LoadPowderBucket",
  "params": {
    "load_position": {"x": 10.0, "y": 20.0, "z": 30.0}
  },
  "req_id": "..."
}
```

#### `FFQ.UnloadPowderBucket`

```json
{
  "cmd": "FFQ.UnloadPowderBucket",
  "params": {
    "unload_position": {"x": 10.0, "y": 20.0, "z": 30.0}
  },
  "req_id": "..."
}
```

#### `FFQ.PickPowder`

```json
{
  "cmd": "FFQ.PickPowder",
  "params": {
    "target_x": 100.0,
    "target_y": 120.0,
    "powder_surface_z": 8.0,
    "pick_depth": 5.0,
    "compact_depth": 2.0
  },
  "req_id": "..."
}
```

#### `FFQ.DispensePowder`

```json
{
  "cmd": "FFQ.DispensePowder",
  "params": {
    "target_position": {"x": 10.0, "y": 20.0, "z": 30.0}
  },
  "req_id": "..."
}
```

---

### 4.6 CLAMP（物料转移）

#### `CLAMP.TransferItem`

```json
{
  "cmd": "CLAMP.TransferItem",
  "params": {
    "source_position": {"x": 10.0, "y": 20.0, "z": 30.0},
    "target_position": {"x": 40.0, "y": 50.0, "z": 60.0},
    "gripper_param": {"position": 15.0, "force": 12.5},
    "release_after_finish": true
  },
  "req_id": "..."
}
```

---

### 4.7 ZD（振荡）

#### `ZD.StartVortex`

```json
{
  "cmd": "ZD.StartVortex",
  "params": {
    "duration": 5000.0
  },
  "req_id": "..."
}
```

---

## 5. 统一认识：这套协议的本质

从代码上看，这个项目的 UDS 协议遵循的是一个统一的“命令-参数-请求 ID”结构：

```json
{
  "cmd": "<Module>.<Function>",
  "params": { ... },
  "req_id": "<uuid>"
}
```

并且响应遵循：

```json
{
  "req_id": "<uuid>",
  "code": 0,
  "msg": "...",
  "result": { ... }
}
```

也就是说，服务端对每个动作提供如下契约：

1. 命令名规范：`Feature.Command`
2. 参数由 JSON 对象承载，不做复杂对象包装
3. 结果通过 `result` 字段返回
4. 用 `req_id` 保证一对一请求响应匹配
5. 用 `code` 判定是否成功，`0` 为成功

---

## 6. 实际代码来源

- [src/unitelabs/usila_c/socket_client.py](../src/unitelabs/usila_c/socket_client.py)
- [src/unitelabs/usila_c/feature/devicebase.py](../src/unitelabs/usila_c/feature/devicebase.py)
- [src/unitelabs/usila_c/feature/wsHandle.py](../src/unitelabs/usila_c/feature/wsHandle.py)
- [src/unitelabs/usila_c/feature/capHandle.py](../src/unitelabs/usila_c/feature/capHandle.py)
- [src/unitelabs/usila_c/feature/lidHandle.py](../src/unitelabs/usila_c/feature/lidHandle.py)
- [src/unitelabs/usila_c/feature/ffqHandle.py](../src/unitelabs/usila_c/feature/ffqHandle.py)
- [src/unitelabs/usila_c/feature/clampHandle.py](../src/unitelabs/usila_c/feature/clampHandle.py)
- [src/unitelabs/usila_c/feature/zdHandle.py](../src/unitelabs/usila_c/feature/zdHandle.py)

如果需要下一步，我也可以继续把这份文档改成更适合对接 C++/下位机的“接口规范版”，例如补充字段类型表、命令编号表和错误码枚举。 
