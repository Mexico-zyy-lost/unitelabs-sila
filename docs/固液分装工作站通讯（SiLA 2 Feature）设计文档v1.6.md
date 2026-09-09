# 固液分装工作站通讯（SiLA 2 Feature）设计文档（含坐标标定）

---

## 1. 文档概述

| 项目 | 内容 |
|------|------|
| 文档名称 | 固液分装工作站通讯 SiLA 2 Feature 设计文档 |
| 版本 | v1.6 |
| 适用设备 | 多轴自动化工作站（含分粉、称重、震荡、转移、开关盖、分液模块） |
| 协议标准 | SiLA 2 (Standard in Lab Automation 2) |
| 通信协议 | gRPC |
| 数据类型格式 | Protocol Buffers (protobuf) |

---

## 2. 坐标系说明（重要）

### 2.1 统一坐标系约定

> **核心原则：所有 Command 中传入的坐标参数均指"逻辑坐标系"中的 (x, y, z)，而非电机坐标。**

```
┌─────────────────────────────────────────────────────────┐
│                    Client（上位机）                       │
│                                                         │
│   传入参数：逻辑坐标系 (x, y, z)                         │
│   例：target_position = (120.5, 85.3, 42.0)            │
│                                                         │
└──────────────────────┬──────────────────────────────────┘
                       │  gRPC 调用
                       ▼
┌─────────────────────────────────────────────────────────┐
│                    Server（SoC 单片机）                   │
│                                                         │
│   1. 根据业务类型选择对应 Z 轴：                          │
│      - 分粉操作 → 分粉Z轴                                │
│      - 夹爪操作 → 夹爪Z轴                                │
│      - 移液操作 → 移液Z轴                                │
│                                                         │
│   2. 根据标定映射表，将逻辑坐标解算为电机坐标：            │
│      逻辑坐标 (x,y,z) ──映射──▶ 电机坐标 (mx,my,mz)     │
│                                                         │
│   3. 下发电机运动指令                                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Z轴选择规则

| 业务模块 | 使用的Z轴 | 说明 |
|----------|-----------|------|
| 分粉（取粉/吐粉/装卸粉桶） | 分粉Z轴 | Server 自动选择 |
| 转移/开关盖（夹爪操作） | 夹爪Z轴 | Server 自动选择 |
| 分液（吸液/排液/装卸Tip） | 移液Z轴 | Server 自动选择 |
| 设备初始化/急停 | 全部Z轴 | 所有轴同时参与 |

### 2.3 标定映射关系

标定建立的是**逻辑坐标系**与**电机坐标系**之间的映射关系。由于 X、Y 为共用轴，仅 Z 轴因模块不同而独立，因此标定的核心是：

- **X轴映射**：逻辑X ↔ 电机X（全局唯一）
- **Y轴映射**：逻辑Y ↔ 电机Y（全局唯一）
- **Z轴映射**：逻辑Z ↔ 电机Z（每个Z轴独立标定）

每个Z轴取 **3对映射点**，用于建立线性/仿射变换关系。

---

## 3. Feature 总览表

| Feature   | 命令 | 属性 |
|---------|------|------|
| 设备基础 | 设备初始化、急停、通用参数设置、坐标标定 | 设备状态、故障原因、X位置、X电机位置、Y位置、Y电机位置、分粉Z位置、分粉Z电机位置、夹爪Z位置、夹爪Z电机位置、移液Z位置、移液Z电机位置、夹爪力矩、夹爪位置 |
| 分粉模块 | 装载粉桶、卸载粉桶、取粉、吐粉 | — |
| 称重模块 | 去皮清零 | 重量 |
| 震荡模块 | 震荡 | — |
| 转移模块 | 转移 | — |
| 容器开关盖 | 开盖、关盖 | — |
| 分液模块 | 安装Tip头、吸液、排液、退Tip头 | — |
| 调试模块 | 夹爪松开、夹爪夹紧、夹爪旋转、夹爪归零、轴单步移动、LED开、LED关、移液器归零 | 移液器气压、移液器工作状态 |
| 视觉模块 | 板位识别 | — |

---

## 4. 通用数据类型定义

### 4.1 统一返回结构体（CommandResult）

```protobuf
message CommandResult {
    bool Success = 1;
    string Message = 2;
    string Data = 3;
}
```

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `Success` | Boolean | 命令执行结果 | `true` / `false` |
| `Message` | String | 人类可读的描述信息 | `"标定成功"` / `"x超出行程,软限位"` |
| `Data` | String | 扩展数据（key-value 键值对集合的 JSON 文本，无扩展数据时为空字符串） | `"{\"axis\":\"powder_z\",\"residual\":\"0.02\"}"` |

### 4.2 状态结构体（Status）

```protobuf
message DeviceStatus {
    int32 Status = 1;    // 0-空闲, 1-运行, 99-故障
    string Message = 2;
}
```

### 4.3 坐标结构体

```protobuf
// 逻辑坐标（Client传入）
message Position3D {
    double X = 1;    // mm
    double Y = 2;    // mm
    double Z = 3;    // mm
}

// 电机坐标（仅标定时使用）
message MotorPosition3D {
    double Mx = 1;   // 电机X (pulse 或 mm)
    double My = 2;   // 电机Y (pulse 或 mm)
    double Mz = 3;   // 电机Z (pulse 或 mm)
}

// 标定映射点对
message CalibrationPair {
    Position3D LogicalPos = 1;      // 逻辑坐标系坐标
    MotorPosition3D MotorPos = 2;   // 电机坐标系坐标
}
```

### 4.4 夹爪参数结构体

```protobuf
message GripperParam {
    double Position = 1;   // 夹爪张开宽度 (mm)
    double Force = 2;      // 夹爪夹持力矩 (N·m)
}
```

---

## 5. Feature：设备基础（DeviceBase）

### 5.1 Feature 元信息

| 属性 | 值 |
|------|-----|
| Identifier | `DeviceBase` |
| DisplayName | 设备基础控制 |
| Description | 提供设备初始化、急停、通用参数设置、坐标标定及状态查询功能 |
| Category | Core |

### 5.2 Commands

#### 5.2.1 设备初始化（Initialize）

| 属性 | 值 |
|------|-----|
| Identifier | `Initialize` |
| DisplayName | 设备初始化 |
| Description | 执行设备上电初始化，包括各轴回零、传感器自检 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| Result | CommandResult | 统一返回结构体 |

---

#### 5.2.2 急停（EmergencyStop）

| 属性 | 值 |
|------|-----|
| Identifier | `EmergencyStop` |
| DisplayName | 急停 |
| Description | 立即停止所有运动，进入安全状态 |
| Observable | 否 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| Result | CommandResult | 统一返回结构体 |

---

#### 5.2.3 通用参数设置（SetGeneralParameters）

| 属性 | 值 |
|------|-----|
| Identifier | `SetGeneralParameters` |
| DisplayName | 通用参数设置 |
| Description | 设置各轴运动速度等通用参数 |
| Observable | 否 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| XSpeed | Real | mm/s | X轴运动速度 |
| YSpeed | Real | mm/s | Y轴运动速度 |
| PowderZSpeed | Real | mm/s | 分粉Z轴速度 |
| GripperZSpeed | Real | mm/s | 夹爪Z轴速度 |
| LiquidZSpeed | Real | mm/s | 分液Z轴速度 |
| GripperSpeed | Real | mm/s | 夹爪开合速度 |
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| Result | CommandResult | 统一返回结构体 |

---

#### 5.2.4 坐标标定（CoordinateCalibration）🆕

| 属性 | 值 |
|------|-----|
| Identifier | `CoordinateCalibration` |
| DisplayName | 坐标标定 |
| Description | 对3个Z轴分别进行坐标系-电机坐标映射标定，每轴取3对映射点 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| PowderZCalibration | List\<CalibrationPair\>（3对映射点） | 分粉Z轴 3对映射点 |
| GripperZCalibration | List\<CalibrationPair\>（3对映射点） | 夹爪Z轴 3对映射点 |
| LiquidZCalibration | List\<CalibrationPair\>（3对映射点） | 移液Z轴 3对映射点 |
| Timeout | Integer | 命令执行超时时间（秒），Client 缺省传 10 |

**CalibrationPair 结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| LogicalPos | Position3D (X,Y,Z) | 逻辑坐标系坐标 (mm) |
| MotorPos | MotorPosition3D (Mx,My,Mz) | 电机坐标系坐标 (pulse/mm) |

**OutputParameter：**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| Result | CommandResult | 统一返回结构体 |

**Data 字段内容示例（key-value 集合序列化后的 JSON 文本）：**

```json
{
    "powder_z_residual": "0.015",
    "gripper_z_residual": "0.008",
    "liquid_z_residual": "0.012",
    "calibration_timestamp": "2026-08-13T13:30:00Z"
}
```

**调用示例：**

```python
CoordinateCalibration(
    PowderZCalibration=[
        # 第1对映射点
        {
            "LogicalPos": {"X": 100.0, "Y": 50.0, "Z": 0.0},
            "MotorPos":   {"Mx": 10000, "My": 5000, "Mz": 0}
        },
        # 第2对映射点
        {
            "LogicalPos": {"X": 100.0, "Y": 50.0, "Z": 25.0},
            "MotorPos":   {"Mx": 10000, "My": 5000, "Mz": 25000}
        },
        # 第3对映射点
        {
            "LogicalPos": {"X": 100.0, "Y": 50.0, "Z": 50.0},
            "MotorPos":   {"Mx": 10000, "My": 5000, "Mz": 50000}
        }
    ],
    GripperZCalibration=[
        {
            "LogicalPos": {"X": 200.0, "Y": 80.0, "Z": 0.0},
            "MotorPos":   {"Mx": 20000, "My": 8000, "Mz": 0}
        },
        {
            "LogicalPos": {"X": 200.0, "Y": 80.0, "Z": 30.0},
            "MotorPos":   {"Mx": 20000, "My": 8000, "Mz": 30000}
        },
        {
            "LogicalPos": {"X": 200.0, "Y": 80.0, "Z": 60.0},
            "MotorPos":   {"Mx": 20000, "My": 8000, "Mz": 60000}
        }
    ],
    LiquidZCalibration=[
        {
            "LogicalPos": {"X": 300.0, "Y": 120.0, "Z": 0.0},
            "MotorPos":   {"Mx": 30000, "My": 12000, "Mz": 0}
        },
        {
            "LogicalPos": {"X": 300.0, "Y": 120.0, "Z": 20.0},
            "MotorPos":   {"Mx": 30000, "My": 12000, "Mz": 20000}
        },
        {
            "LogicalPos": {"X": 300.0, "Y": 120.0, "Z": 40.0},
            "MotorPos":   {"Mx": 30000, "My": 12000, "Mz": 40000}
        }
    ],
    Timeout=30
)
```


---

### 5.3 Properties

| Property Identifier | DisplayName | 类型 | Observable | 说明 |
|---------------------|-------------|------|------------|------|
| `DeviceState` | 设备状态 | int | 是 | 0-空闲, 1-运行, 99-故障 |
| `FaultReason` | 故障原因 | string | 是 | 故障描述信息 |
| `XPosition` | X位置 | double | 是 | X轴当前位置 (mm)，逻辑坐标 |
| `XMotorPosition` | X电机位置 | double | 是 | X轴当前位置 (mm)，物理电机坐标 |
| `YPosition` | Y位置 | double | 是 | Y轴当前位置 (mm)，逻辑坐标 |
| `YMotorPosition` | Y电机位置 | double | 是 | Y轴当前位置 (mm)，物理电机坐标 |
| `PowderZPosition` | 分粉Z位置 | double | 是 | 分粉Z轴当前位置 (mm)，逻辑坐标 |
| `PowderZMotorPosition` | 分粉Z电机位置 | double | 是 | 分粉Z轴当前位置 (mm)，物理电机坐标 |
| `GripperZPosition` | 夹爪Z位置 | double | 是 | 夹爪Z轴当前位置 (mm)，逻辑坐标 |
| `GripperZMotorPosition` | 夹爪Z电机位置 | double | 是 | 夹爪Z轴当前位置 (mm)，物理电机坐标 |
| `LiquidZPosition` | 移液Z位置 | double | 是 | 移液Z轴当前位置 (mm)，逻辑坐标 |
| `LiquidZMotorPosition` | 移液Z电机位置 | double | 是 | 移液Z轴当前位置 (mm)，物理电机坐标 |
| `GripperForce` | 夹爪力矩 | double | 是 | 夹爪当前力矩 (N·m) |
| `GripperPosition` | 夹爪位置 | double | 是 | 夹爪当前张开宽度 (mm) |

> **注意：** 位置类 Property 单位均为 mm：`xxxPosition` 为逻辑坐标（Server 内部已完成电机坐标→逻辑坐标的反向解算），`xxxMotorPosition` 为物理电机坐标（原始值直接上报）。

---

## 6. Feature：分粉模块（PowderDosing）

### 6.1 Feature 元信息

| 属性 | 值 |
|------|-----|
| Identifier | `PowderDosing` |
| DisplayName | 分粉模块 |
| Description | 提供粉体装载、卸载、取粉、吐粉功能 |
| Category | Application |

### 6.2 Commands

#### 6.2.1 装载粉桶（LoadPowderBucket）

| 属性 | 值 |
|------|-----|
| Identifier | `LoadPowderBucket` |
| DisplayName | 装载粉桶 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| Type | Integer | — | 粉桶类型，1 或 2（两种分装粉管操作方式不同，Server 按类型执行对应动作序列） |
| LoadPosition | Position3D | mm | 装载位置（逻辑坐标） |
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：** CommandResult

> Server 自动选择 **分粉Z轴**，解算电机坐标后执行。

---

#### 6.2.2 卸载粉桶（UnloadPowderBucket）

| 属性 | 值 |
|------|-----|
| Identifier | `UnloadPowderBucket` |
| DisplayName | 卸载粉桶 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| Type | Integer | — | 粉桶类型，1 或 2（两种分装粉管操作方式不同，Server 按类型执行对应动作序列） |
| UnloadPosition | Position3D | mm | 卸载位置（逻辑坐标） |
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：** CommandResult

---

#### 6.2.3 取粉（PickPowder）

| 属性 | 值 |
|------|-----|
| Identifier | `PickPowder` |
| DisplayName | 取粉 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| Type | Integer | — | 粉桶类型，1 或 2（两种分装粉管操作方式不同，Server 按类型执行对应动作序列） |
| TargetX | Real | mm | 目标X（逻辑坐标） |
| TargetY | Real | mm | 目标Y（逻辑坐标） |
| PowderSurfaceZ | Real | mm | 粉面高度Z（逻辑坐标） |
| PickDepth | Real | mm | 取粉深度 |
| CompactDepth | Real | mm | 压实深度 |
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：** CommandResult

> Server 自动选择 **分粉Z轴**。

---

#### 6.2.4 吐粉（DispensePowder）

| 属性 | 值 |
|------|-----|
| Identifier | `DispensePowder` |
| DisplayName | 吐粉 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| Type | Integer | — | 粉桶类型，1 或 2（两种分装粉管操作方式不同，Server 按类型执行对应动作序列） |
| TargetPosition | Position3D | mm | 吐粉目标位置（逻辑坐标） |
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：** CommandResult

---

## 7. Feature：称重模块（Weighing）

### 7.1 Commands

#### 7.1.1 去皮清零（Tare）

| 属性 | 值 |
|------|-----|
| Identifier | `Tare` |
| DisplayName | 去皮清零 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：** CommandResult

### 7.2 Properties

| Property Identifier | DisplayName | 类型 | Observable | 说明 |
|---------------------|-------------|------|------------|------|
| `Weight` | 重量 | double | 是 | 当前称重值 (mg) |

---

## 8. Feature：震荡模块（Vortex）

### 8.1 Commands

#### 8.1.1 震荡（StartVortex）

| 属性 | 值 |
|------|-----|
| Identifier | `StartVortex` |
| DisplayName | 震荡 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| Duration | Real | ms | 震荡时长 |
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：** CommandResult

---

## 9. Feature：转移模块（Transfer）

### 9.1 Commands

#### 9.1.1 转移（TransferItem）

| 属性 | 值 |
|------|-----|
| Identifier | `TransferItem` |
| DisplayName | 转移 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| SourcePosition | Position3D | mm | 源位置（逻辑坐标） |
| TargetPosition | Position3D | mm | 目标位置（逻辑坐标） |
| GripperParam | GripperParam | — | 夹爪参数 |
| ReleaseAfterFinish | Boolean | — | 是否松开夹爪 |
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：** CommandResult

> Server 自动选择 **夹爪Z轴**。

---

## 10. Feature：容器开关盖模块（LidHandling）

### 10.1 Commands

#### 10.1.1 开关盖（ToggleLid）

| 属性 | 值 |
|------|-----|
| Identifier | `ToggleLid` |
| DisplayName | 开关盖 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| Mode | String | — | 操作模式："open"=开盖，"close"=关盖 |
| ContainerDiameter | Real | mm | 容器直径（操作前用于夹紧瓶身，即挤压行程） |
| OpenPosition | Position3D | mm | 操作位置（开盖/关盖共用，关盖时复用此位置） |
| LidPlacePosition | Position3D | mm | 盖子放置位置（仅开盖时使用） |
| OpenGripperParam | GripperParam | — | 开盖夹爪参数 |
| CloseGripperParam | GripperParam | — | 关盖夹爪参数 |
| RotationCycles | Integer | 圈 | 旋转圈数 |
| RotationSpeed | Real | rpm | 旋转速度 |
| RotationForce | Real | N·m | 旋转力矩 |
| ZLiftHeight | Real | mm | Z抬升高度 |
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：** CommandResult

> Server 自动选择 **夹爪Z轴**。mode="open"时执行开盖流程（夹紧→旋开→放盖），mode="close"时执行关盖流程（取盖→旋紧→释放），关盖位置复用 open_position。

---

## 11. Feature：分液模块（LiquidHandling）

### 11.1 Commands

#### 11.1.1 安装Tip头（AttachTip）

| 属性 | 值 |
|------|-----|
| Identifier | `AttachTip` |
| DisplayName | 安装Tip头 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| TipPosition | Position3D | mm | Tip位置（逻辑坐标） |
| PressForce | Real | N | 压装力 |
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：** CommandResult

> Server 自动选择 **移液Z轴**。

---

#### 11.1.2 吸液（Aspirate）

| 属性 | 值 |
|------|-----|
| Identifier | `Aspirate` |
| DisplayName | 吸液 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| TargetPosition | Position3D | mm | 吸液位置（逻辑坐标） |
| Volume | Real | μL | 吸液体积 |
| AspirateSpeed | Real | μL/s | 吸液速度 |
| ImmersionDepth | Real | mm | 浸入深度 |
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：** CommandResult

---

#### 11.1.3 排液（Dispense）

| 属性 | 值 |
|------|-----|
| Identifier | `Dispense` |
| DisplayName | 排液 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| TargetPosition | Position3D | mm | 排液位置（逻辑坐标） |
| Volume | Real | μL | 排液体积 |
| DispenseSpeed | Real | μL/s | 排液速度 |
| ImmersionDepth | Real | mm | 浸入深度 |
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：** CommandResult

---

#### 11.1.4 退Tip头（EjectTip）

| 属性 | 值 |
|------|-----|
| Identifier | `EjectTip` |
| DisplayName | 退Tip头 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| EjectPosition | Position3D | mm | 退Tip位置（逻辑坐标） |
| EjectForce | Real | N | 退Tip力 |
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：** CommandResult

---

## 12. Feature：视觉模块（Vision）

### 12.1 Feature 元信息

| 属性 | 值 |
|------|-----|
| Identifier | `Vision` |
| DisplayName | 视觉模块 |
| Description | 提供板位视觉识别能力，返回各板位的板类型、置信度、包围盒与中心点 |
| Category | Application |

### 12.2 Commands

#### 12.2.1 板位识别（PlateRecognize）

| 属性 | 值 |
|------|-----|
| Identifier | `PlateRecognize` |
| DisplayName | 板位识别 |
| Description | 对工作站所有板位执行一次视觉识别，返回各板位的板类型、置信度、包围盒与中心点 |
| Observable | 是 |

**InputParameter：**

| 参数名 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| Timeout | Integer | s | 命令执行超时时间，Client 缺省传 10 |

**OutputParameter：**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| Result | PlateRecognitionResult | 板位识别结果（强类型结构） |

> **注意：** 本命令输出不使用统一 CommandResult，直接返回强类型 `PlateRecognitionResult` 结构。

**PlateRecognitionResult 结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| code | int | 返回码，0 表示成功 |
| msg | string | 返回消息 |
| cost_ms | double | 识别耗时 (ms) |
| image_base64 | string | 识别图像（base64，可为空） |
| detect_list | PlateDetectItem[] | 检测结果列表（每个板位一条） |

**PlateDetectItem 结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| station | string | 板位编号（如 B1、C3） |
| plate_type | string | 板类型（如 96-well-plate、24-well-plate、12-well-plate、96-Thermo-Tube）；空字符串表示未检出 |
| score | double | 置信度（0~1），未检出时为 0 |
| box | double[4] | 包围盒 [x1, y1, x2, y2]，图像像素坐标 |
| center | double[2] | 中心点 [x, y]，图像像素坐标 |

**返回值约定：**

- `code = 0` 表示识别调用成功，非 0 表示失败，失败原因见 `msg`；
- 某板位 `plate_type` 为空字符串且 `score = 0`、`box`/`center` 为空数组，表示该板位未检测到板；
- `box` 为左上、右下格式的图像像素包围盒，`center` 为板面像素中心点。

**约束：**

- `image_base64` 经 FDL（String）传输，gRPC 单条消息默认上限 4MB，base64 编码膨胀约 33%，Server 端返回前应做 JPEG 压缩/降采样，原图控制在 3MB 以内；
- 板位识别为低频操作，不应高频调用。

**返回示例：**

```json
{
    "code": 0,
    "msg": "success",
    "cost_ms": 172.22,
    "image_base64": "",
    "detect_list": [
        {
            "station": "B1",
            "plate_type": "96-well-plate",
            "score": 0.775,
            "box": [256.5, 480.9, 448.2, 717.2],
            "center": [352.4, 599.1]
        },
        {
            "station": "B2",
            "plate_type": "",
            "score": 0,
            "box": [],
            "center": []
        },
        {
            "station": "B3",
            "plate_type": "24-well-plate",
            "score": 0.676,
            "box": [317.6, 60.3, 472.5, 252.8],
            "center": [395.1, 156.5]
        },
        {
            "station": "C1",
            "plate_type": "24-well-plate",
            "score": 0.841,
            "box": [448.3, 468.3, 643.9, 722.5],
            "center": [546.1, 595.4]
        },
        {
            "station": "C2",
            "plate_type": "12-well-plate",
            "score": 0.81,
            "box": [454.4, 204.1, 648.8, 455.5],
            "center": [551.6, 329.8]
        },
        {
            "station": "C3",
            "plate_type": "24-well-plate",
            "score": 0.842,
            "box": [484.7, 42.2, 646.9, 200.1],
            "center": [565.8, 121.2]
        },
        {
            "station": "D1",
            "plate_type": "96-Thermo-Tube",
            "score": 0.971,
            "box": [671.9, 469.2, 861.3, 722.3],
            "center": [766.6, 595.8]
        },
        {
            "station": "D2",
            "plate_type": "12-well-plate",
            "score": 0.443,
            "box": [658.5, 25.1, 853.8, 441.7],
            "center": [756.1, 233.4]
        },
        {
            "station": "D3",
            "plate_type": "",
            "score": 0,
            "box": [],
            "center": []
        }
    ]
}
```

---

## 13. 设计约束与注意事项

| 编号 | 约束项 | 说明 |
|------|--------|------|
| 1 | 坐标系统一 | **所有 Command 入参均为逻辑坐标系 (x,y,z)**，Server 负责解算电机坐标 |
| 2 | Z轴自动选择 | Server 根据业务模块自动选择对应Z轴，Client 无需感知 |
| 3 | 标定前置 | 首次使用或更换机械结构后，必须先执行 CoordinateCalibration |
| 4 | 单命令执行 | 同一时刻仅接受一个 Observable Command |
| 5 | 急停优先 | EmergencyStop 可在任何状态下执行 |
| 6 | 幂等性 | 所有 Command 设计为幂等 |
| 7 | 超时机制 | 所有 Command 均含 Timeout 入参（Integer，单位秒，Client 缺省传 10）；命令在超时时间内未完成视为执行失败 |
| 8 | 状态互斥 | FAULT(99) 时仅接受 EmergencyStop 和 Initialize |
| 9 | 单位规范 | 坐标:mm，速度:mm/s或rpm，时长:ms，重量:mg，体积:μL，力矩:N·m |

---

## 14. 错误处理规范

| 错误码 | 名称 | 说明 |
|--------|------|------|
| 0 | SUCCESS | 成功 |
| 1001 | AXIS_OVER_TRAVEL | 轴超程（软限位） |
| 1002 | AXIS_HARD_LIMIT | 硬限位触发 |
| 1003 | GRIPPER_FORCE_EXCEEDED | 夹爪力矩超限 |
| 1004 | CALIBRATION_FAILED | 标定拟合残差超限 |
| 1005 | CALIBRATION_DATA_INVALID | 标定数据无效（点数不足/共线） |
| 2001 | POWDER_NOT_FOUND | 未检测到粉体 |
| 2002 | BUCKET_NOT_DETECTED | 粉桶未检测到 |
| 3001 | WEIGHT_UNSTABLE | 称重不稳定 |
| 4001 | TIP_ATTACH_FAILED | Tip安装失败 |
| 4002 | LIQUID_NOT_DETECTED | 液面检测失败 |
| 5001 | LID_STUCK | 盖子卡住 |
| 9999 | UNKNOWN_ERROR | 未知错误 |

---

## 15. 版本历史

| 版本 | 日期 | 修改内容 | 作者 |
|------|------|----------|------|
| v1.0 | 2026-08-13 | 初始版本 | — |
| v1.1 | 2026-08-13 | 新增 CoordinateCalibration 命令；新增坐标系说明章节 | — |
| v1.2 | 2026-08-13 | FDL 补充元数据属性（Category/FeatureVersion/FeatureContentVersion/Originator）；CommandResult.data 改为 KeyValuePair 键值对集合；Feature 总览表移至第 3 章并中文化，章节重新编号；震荡参数改为时长(ms)；开盖新增容器直径参数；称重单位改为 mg；新增 5 个电机坐标 Property；新增 Debug 调试模式 Feature | — |
| v1.3 | 2026-08-14 | 新增视觉模块 Vision Feature：板位识别命令（PlateRecognize，无入参），输出打破 CommandResult 约定，直接返回强类型 PlateRecognitionResult 结构（含 PlateDetectItem 检测项）；图像 base64 经 FDL 传输并标注 4MB 消息大小约束；章节重新编号 | — |
| v1.4 | 2026-08-19 | LidHandling：OpenLid + CloseLid 合并为单一命令 ToggleLid，新增 mode 参数（string，"open"/"close"）区分操作模式，关盖位置复用 open_position | — |
| v1.5 | 2026-08-21 | CommandResult.Data 由 List\<KeyValuePair\> 改为 String（key-value 集合的 JSON 文本）；所有 Command 统一新增 Timeout 入参（Integer，单位秒，Client 缺省传 10）；全文参数标识统一为 PascalCase（对齐实际 FDL 文件）；附录 A 重写为 9 个 Feature 的实际 FDL 文件分节收录 | — |
| v1.6 | 2026-08-24 | PowderDosing：因存在两种操作方式完全不同的分装粉管，LoadPowderBucket / UnloadPowderBucket / PickPowder / DispensePowder 四个命令统一新增 Type 入参（Integer，粉桶类型 1 或 2，置于首参数位）；FDL 文件版本保持 1.0 不变 | — |

---

# 附录A：完整 FDL 文件

以下 9 个 FDL 文件与代码库 `PB.AutoSuite.App\data\fdl\` 目录下的实际文件保持一致（单一数据源，MockServer / HMI 均直接引用该目录）。

## 附录A.1：DeviceBase（DeviceBase_v1.0.sila.xml）

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Feature xmlns="http://www.sila-standard.org" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" Category="core" FeatureVersion="1.0" Originator="com.pharmablock" MaturityLevel="Draft" SiLA2Version="2.0">

    <!-- ============================================================ -->
    <!-- Feature: DeviceBase 设备基础控制 -->
    <!-- ============================================================ -->
    <Identifier>DeviceBase</Identifier>
    <DisplayName>设备基础控制</DisplayName>
    <Description>提供设备初始化、急停、通用参数设置、坐标标定及状态查询功能</Description>

    <!-- ==================== DataTypes ==================== -->
    <DataTypeDefinition>
        <Identifier>CommandResult</Identifier>
        <DisplayName>统一返回结构体</DisplayName>
        <Description>命令统一返回结构：执行结果 + 描述信息 + 扩展数据</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Success</Identifier>
                    <DisplayName>执行结果</DisplayName>
                    <Description>命令执行结果（true成功/false失败）</Description>
                    <DataType><Basic>Boolean</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Message</Identifier>
                    <DisplayName>描述信息</DisplayName>
                    <Description>人类可读的描述信息</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Data</Identifier>
                    <DisplayName>扩展数据</DisplayName>
                    <Description>扩展数据（key-value字典集合）</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <DataTypeDefinition>
        <Identifier>Position3D</Identifier>
        <DisplayName>逻辑坐标</DisplayName>
        <Description>逻辑坐标系中的三维坐标，单位mm</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>X</Identifier>
                    <DisplayName>X坐标</DisplayName>
                    <Description>X坐标(mm)</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Y</Identifier>
                    <DisplayName>Y坐标</DisplayName>
                    <Description>Y坐标(mm)</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Z</Identifier>
                    <DisplayName>Z坐标</DisplayName>
                    <Description>Z坐标(mm)</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <DataTypeDefinition>
        <Identifier>MotorPosition3D</Identifier>
        <DisplayName>电机坐标</DisplayName>
        <Description>电机坐标系中的三维坐标</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Mx</Identifier>
                    <DisplayName>电机X</DisplayName>
                    <Description>电机X坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>My</Identifier>
                    <DisplayName>电机Y</DisplayName>
                    <Description>电机Y坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Mz</Identifier>
                    <DisplayName>电机Z</DisplayName>
                    <Description>电机Z坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <DataTypeDefinition>
        <Identifier>CalibrationPair</Identifier>
        <DisplayName>标定映射点对</DisplayName>
        <Description>一对逻辑坐标与电机坐标的映射</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>LogicalPos</Identifier>
                    <DisplayName>逻辑坐标</DisplayName>
                    <Description>逻辑坐标系中的坐标</Description>
                    <DataType><DataTypeIdentifier>Position3D</DataTypeIdentifier></DataType>
                </Element>
                <Element>
                    <Identifier>MotorPos</Identifier>
                    <DisplayName>电机坐标</DisplayName>
                    <Description>电机坐标系中的坐标</Description>
                    <DataType><DataTypeIdentifier>MotorPosition3D</DataTypeIdentifier></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <DataTypeDefinition>
        <Identifier>GripperParam</Identifier>
        <DisplayName>夹爪参数</DisplayName>
        <Description>夹爪宽度与夹持力矩参数</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Position</Identifier>
                    <DisplayName>夹爪宽度(mm)</DisplayName>
                    <Description>夹爪张开宽度(mm)</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Force</Identifier>
                    <DisplayName>夹持力矩(N·m)</DisplayName>
                    <Description>夹持力矩(N·m)</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <!-- ==================== Commands ==================== -->

    <!-- Initialize -->
    <Command>
        <Identifier>Initialize</Identifier>
        <DisplayName>设备初始化</DisplayName>
        <Description>执行设备上电初始化，包括各轴回零、传感器自检</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>命令执行结果</Description>
            <DataType><DataTypeIdentifier>CommandResult</DataTypeIdentifier></DataType>
        </Response>
    </Command>

    <!-- EmergencyStop -->
    <Command>
        <Identifier>EmergencyStop</Identifier>
        <DisplayName>急停</DisplayName>
        <Description>立即停止所有运动，进入安全状态</Description>
        <Observable>No</Observable>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>命令执行结果</Description>
            <DataType><DataTypeIdentifier>CommandResult</DataTypeIdentifier></DataType>
        </Response>
    </Command>

    <!-- SetGeneralParameters -->
    <Command>
        <Identifier>SetGeneralParameters</Identifier>
        <DisplayName>通用参数设置</DisplayName>
        <Description>设置各轴运动速度等通用参数</Description>
        <Observable>No</Observable>
        <Parameter>
            <Identifier>XSpeed</Identifier>
            <DisplayName>X轴速度(mm/s)</DisplayName>
            <Description>X轴运动速度(mm/s)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>YSpeed</Identifier>
            <DisplayName>Y轴速度(mm/s)</DisplayName>
            <Description>Y轴运动速度(mm/s)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>PowderZSpeed</Identifier>
            <DisplayName>分粉Z速度(mm/s)</DisplayName>
            <Description>分粉Z轴运动速度(mm/s)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>GripperZSpeed</Identifier>
            <DisplayName>夹爪Z速度(mm/s)</DisplayName>
            <Description>夹爪Z轴运动速度(mm/s)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>LiquidZSpeed</Identifier>
            <DisplayName>分液Z速度(mm/s)</DisplayName>
            <Description>分液Z轴运动速度(mm/s)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>GripperSpeed</Identifier>
            <DisplayName>夹爪速度(mm/s)</DisplayName>
            <Description>夹爪开合速度(mm/s)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>命令执行结果</Description>
            <DataType><DataTypeIdentifier>CommandResult</DataTypeIdentifier></DataType>
        </Response>
    </Command>

    <!-- CoordinateCalibration -->
    <Command>
        <Identifier>CoordinateCalibration</Identifier>
        <DisplayName>坐标标定</DisplayName>
        <Description>对3个Z轴分别进行坐标系-电机坐标映射标定，每轴取3对映射点。所有业务Command传入的坐标均为逻辑坐标系，Server根据此标定数据进行电机坐标解算。</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>PowderZCalibration</Identifier>
            <DisplayName>分粉Z轴标定数据(3对)</DisplayName>
            <Description>分粉Z轴的3对逻辑坐标-电机坐标映射点</Description>
            <DataType>
                <List>
                    <DataType><DataTypeIdentifier>CalibrationPair</DataTypeIdentifier></DataType>
                </List>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>GripperZCalibration</Identifier>
            <DisplayName>夹爪Z轴标定数据(3对)</DisplayName>
            <Description>夹爪Z轴的3对逻辑坐标-电机坐标映射点</Description>
            <DataType>
                <List>
                    <DataType><DataTypeIdentifier>CalibrationPair</DataTypeIdentifier></DataType>
                </List>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>LiquidZCalibration</Identifier>
            <DisplayName>移液Z轴标定数据(3对)</DisplayName>
            <Description>移液Z轴的3对逻辑坐标-电机坐标映射点</Description>
            <DataType>
                <List>
                    <DataType><DataTypeIdentifier>CalibrationPair</DataTypeIdentifier></DataType>
                </List>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>命令执行结果</Description>
            <DataType><DataTypeIdentifier>CommandResult</DataTypeIdentifier></DataType>
        </Response>
    </Command>

    <!-- ==================== Properties ==================== -->

    <Property>
        <Identifier>DeviceState</Identifier>
        <DisplayName>设备状态</DisplayName>
        <Description>0-空闲, 1-运行, 99-故障</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Integer</Basic></DataType>
    </Property>

    <Property>
        <Identifier>FaultReason</Identifier>
        <DisplayName>故障原因</DisplayName>
        <Description>当前故障描述，无故障时为空字符串</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>String</Basic></DataType>
    </Property>

    <Property>
        <Identifier>XPosition</Identifier>
        <DisplayName>X位置</DisplayName>
        <Description>X轴当前逻辑坐标(mm)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

    <Property>
        <Identifier>XMotorPosition</Identifier>
        <DisplayName>X电机位置</DisplayName>
        <Description>X轴当前物理电机坐标(mm)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

    <Property>
        <Identifier>YPosition</Identifier>
        <DisplayName>Y位置</DisplayName>
        <Description>Y轴当前逻辑坐标(mm)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

    <Property>
        <Identifier>YMotorPosition</Identifier>
        <DisplayName>Y电机位置</DisplayName>
        <Description>Y轴当前物理电机坐标(mm)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

    <Property>
        <Identifier>PowderZPosition</Identifier>
        <DisplayName>分粉Z位置</DisplayName>
        <Description>分粉Z轴当前逻辑坐标(mm)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

    <Property>
        <Identifier>PowderZMotorPosition</Identifier>
        <DisplayName>分粉Z电机位置</DisplayName>
        <Description>分粉Z轴当前物理电机坐标(mm)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

    <Property>
        <Identifier>GripperZPosition</Identifier>
        <DisplayName>夹爪Z位置</DisplayName>
        <Description>夹爪Z轴当前逻辑坐标(mm)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

    <Property>
        <Identifier>GripperZMotorPosition</Identifier>
        <DisplayName>夹爪Z电机位置</DisplayName>
        <Description>夹爪Z轴当前物理电机坐标(mm)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

    <Property>
        <Identifier>LiquidZPosition</Identifier>
        <DisplayName>移液Z位置</DisplayName>
        <Description>移液Z轴当前逻辑坐标(mm)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

    <Property>
        <Identifier>LiquidZMotorPosition</Identifier>
        <DisplayName>移液Z电机位置</DisplayName>
        <Description>移液Z轴当前物理电机坐标(mm)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

    <Property>
        <Identifier>GripperForce</Identifier>
        <DisplayName>夹爪力矩</DisplayName>
        <Description>夹爪当前力矩(N·m)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

    <Property>
        <Identifier>GripperPosition</Identifier>
        <DisplayName>夹爪位置</DisplayName>
        <Description>夹爪当前张开宽度(mm)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

</Feature>
```

## 附录A.2：PowderDosing（PowderDosing_v1.0.sila.xml）

```xml
<?xml version="1.0" encoding="utf-8"?>
<Feature xmlns="http://www.sila-standard.org" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" Category="application" FeatureVersion="1.0" Originator="com.pharmablock" MaturityLevel="Draft" SiLA2Version="2.0">

    <!-- ============================================================ -->
    <!-- Feature: PowderDosing 分粉模块 -->
    <!-- ============================================================ -->
    <Identifier>PowderDosing</Identifier>
    <DisplayName>分粉模块</DisplayName>
    <Description>提供粉体装载、卸载、取粉、吐粉功能。所有坐标参数均为逻辑坐标系，Server自动选择分粉Z轴解算。</Description>

    <!-- ==================== DataTypes ==================== -->
    <DataTypeDefinition>
        <Identifier>CommandResult</Identifier>
        <DisplayName>统一返回结构体</DisplayName>
        <Description>统一返回结构体</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Success</Identifier>
                    <DisplayName>执行结果</DisplayName>
                    <Description>执行结果</Description>
                    <DataType><Basic>Boolean</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Message</Identifier>
                    <DisplayName>描述信息</DisplayName>
                    <Description>描述信息</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Data</Identifier>
                    <DisplayName>扩展数据</DisplayName>
                    <Description>扩展数据</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <DataTypeDefinition>
        <Identifier>Position3D</Identifier>
        <DisplayName>逻辑坐标</DisplayName>
        <Description>逻辑坐标系中的三维坐标，单位mm</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>X</Identifier>
                    <DisplayName>X坐标</DisplayName>
                    <Description>X坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Y</Identifier>
                    <DisplayName>Y坐标</DisplayName>
                    <Description>Y坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Z</Identifier>
                    <DisplayName>Z坐标</DisplayName>
                    <Description>Z坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <!-- ==================== Commands ==================== -->

    <!-- LoadPowderBucket -->
    <Command>
        <Identifier>LoadPowderBucket</Identifier>
        <DisplayName>装载粉桶</DisplayName>
        <Description>将粉桶装载到指定位置（逻辑坐标）</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Type</Identifier>
            <DisplayName>粉桶类型</DisplayName>
            <Description>粉桶类型：1 或 2（两种分装粉管操作方式不同，Server 按类型执行对应动作序列）</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>LoadPosition</Identifier>
            <DisplayName>装载位置</DisplayName>
            <Description>装载位置</Description>
            <DataType>
                <DataTypeIdentifier>Position3D</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- UnloadPowderBucket -->
    <Command>
        <Identifier>UnloadPowderBucket</Identifier>
        <DisplayName>卸载粉桶</DisplayName>
        <Description>将粉桶卸载到指定位置（逻辑坐标）</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Type</Identifier>
            <DisplayName>粉桶类型</DisplayName>
            <Description>粉桶类型：1 或 2（两种分装粉管操作方式不同，Server 按类型执行对应动作序列）</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>UnloadPosition</Identifier>
            <DisplayName>卸载位置</DisplayName>
            <Description>卸载位置</Description>
            <DataType>
                <DataTypeIdentifier>Position3D</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- PickPowder -->
    <Command>
        <Identifier>PickPowder</Identifier>
        <DisplayName>取粉</DisplayName>
        <Description>从粉桶中取粉（逻辑坐标）</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Type</Identifier>
            <DisplayName>粉桶类型</DisplayName>
            <Description>粉桶类型：1 或 2（两种分装粉管操作方式不同，Server 按类型执行对应动作序列）</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>TargetX</Identifier>
            <DisplayName>目标X(mm)</DisplayName>
            <Description>目标X(mm)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>TargetY</Identifier>
            <DisplayName>目标Y(mm)</DisplayName>
            <Description>目标Y(mm)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>PowderSurfaceZ</Identifier>
            <DisplayName>粉面高度Z(mm)</DisplayName>
            <Description>粉面高度Z(mm)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>PickDepth</Identifier>
            <DisplayName>取粉深度(mm)</DisplayName>
            <Description>取粉深度(mm)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>CompactDepth</Identifier>
            <DisplayName>压实深度(mm)</DisplayName>
            <Description>压实深度(mm)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- DispensePowder -->
    <Command>
        <Identifier>DispensePowder</Identifier>
        <DisplayName>吐粉</DisplayName>
        <Description>将粉体吐出到目标位置（逻辑坐标）</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Type</Identifier>
            <DisplayName>粉桶类型</DisplayName>
            <Description>粉桶类型：1 或 2（两种分装粉管操作方式不同，Server 按类型执行对应动作序列）</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>TargetPosition</Identifier>
            <DisplayName>目标位置</DisplayName>
            <Description>目标位置</Description>
            <DataType>
                <DataTypeIdentifier>Position3D</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

</Feature>
```

## 附录A.3：Weighing（Weighing_v1.0.sila.xml）

```xml
<?xml version="1.0" encoding="utf-8"?>
<Feature xmlns="http://www.sila-standard.org" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" Category="application" FeatureVersion="1.0" Originator="com.pharmablock" MaturityLevel="Draft" SiLA2Version="2.0">

    <!-- ============================================================ -->
    <!-- Feature: Weighing 称重模块 -->
    <!-- ============================================================ -->
    <Identifier>Weighing</Identifier>
    <DisplayName>称重模块</DisplayName>
    <Description>提供称重去皮清零及重量读取功能</Description>

    <!-- ==================== DataTypes ==================== -->
    <DataTypeDefinition>
        <Identifier>CommandResult</Identifier>
        <DisplayName>统一返回结构体</DisplayName>
        <Description>统一返回结构体</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Success</Identifier>
                    <DisplayName>执行结果</DisplayName>
                    <Description>执行结果</Description>
                    <DataType><Basic>Boolean</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Message</Identifier>
                    <DisplayName>描述信息</DisplayName>
                    <Description>描述信息</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Data</Identifier>
                    <DisplayName>扩展数据</DisplayName>
                    <Description>扩展数据</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <!-- ==================== Commands ==================== -->

    <!-- Tare -->
    <Command>
        <Identifier>Tare</Identifier>
        <DisplayName>去皮清零</DisplayName>
        <Description>将当前重量设为零点</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- ==================== Properties ==================== -->

    <!-- Weight Property -->
    <Property>
        <Identifier>Weight</Identifier>
        <DisplayName>重量</DisplayName>
        <Description>当前称重值(mg)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

</Feature>
```

## 附录A.4：Vortex（Vortex_v1.0.sila.xml）

```xml
<?xml version="1.0" encoding="utf-8"?>
<Feature xmlns="http://www.sila-standard.org" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" Category="application" FeatureVersion="1.0" Originator="com.pharmablock" MaturityLevel="Draft" SiLA2Version="2.0">

    <!-- ============================================================ -->
    <!-- Feature: Vortex 震荡模块 -->
    <!-- ============================================================ -->
    <Identifier>Vortex</Identifier>
    <DisplayName>震荡模块</DisplayName>
    <Description>提供震荡混匀功能</Description>

    <!-- ==================== DataTypes ==================== -->
    <DataTypeDefinition>
        <Identifier>CommandResult</Identifier>
        <DisplayName>统一返回结构体</DisplayName>
        <Description>统一返回结构体</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Success</Identifier>
                    <DisplayName>执行结果</DisplayName>
                    <Description>执行结果</Description>
                    <DataType><Basic>Boolean</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Message</Identifier>
                    <DisplayName>描述信息</DisplayName>
                    <Description>描述信息</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Data</Identifier>
                    <DisplayName>扩展数据</DisplayName>
                    <Description>扩展数据</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <!-- ==================== Commands ==================== -->

    <!-- StartVortex -->
    <Command>
        <Identifier>StartVortex</Identifier>
        <DisplayName>震荡</DisplayName>
        <Description>按指定时长执行震荡混匀</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Duration</Identifier>
            <DisplayName>震荡时长(ms)</DisplayName>
            <Description>震荡时长(ms)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

</Feature>
```

## 附录A.5：Transfer（Transfer_v1.0.sila.xml）

```xml
<?xml version="1.0" encoding="utf-8"?>
<Feature xmlns="http://www.sila-standard.org" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" Category="application" FeatureVersion="1.0" Originator="com.pharmablock" MaturityLevel="Draft" SiLA2Version="2.0">

    <!-- ============================================================ -->
    <!-- Feature: Transfer 转移模块 -->
    <!-- ============================================================ -->
    <Identifier>Transfer</Identifier>
    <DisplayName>转移模块</DisplayName>
    <Description>提供容器/耗材的夹取转移功能。所有坐标为逻辑坐标系，Server自动选择夹爪Z轴。</Description>

    <!-- ==================== DataTypes ==================== -->
    <DataTypeDefinition>
        <Identifier>CommandResult</Identifier>
        <DisplayName>统一返回结构体</DisplayName>
        <Description>统一返回结构体</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Success</Identifier>
                    <DisplayName>执行结果</DisplayName>
                    <Description>执行结果</Description>
                    <DataType><Basic>Boolean</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Message</Identifier>
                    <DisplayName>描述信息</DisplayName>
                    <Description>描述信息</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Data</Identifier>
                    <DisplayName>扩展数据</DisplayName>
                    <Description>扩展数据</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <DataTypeDefinition>
        <Identifier>Position3D</Identifier>
        <DisplayName>逻辑坐标</DisplayName>
        <Description>逻辑坐标系中的三维坐标，单位mm</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>X</Identifier>
                    <DisplayName>X坐标</DisplayName>
                    <Description>X坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Y</Identifier>
                    <DisplayName>Y坐标</DisplayName>
                    <Description>Y坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Z</Identifier>
                    <DisplayName>Z坐标</DisplayName>
                    <Description>Z坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <DataTypeDefinition>
        <Identifier>GripperParam</Identifier>
        <DisplayName>夹爪参数</DisplayName>
        <Description>夹爪参数</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Position</Identifier>
                    <DisplayName>夹爪宽度(mm)</DisplayName>
                    <Description>夹爪宽度(mm)</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Force</Identifier>
                    <DisplayName>夹持力矩(N·m)</DisplayName>
                    <Description>夹持力矩(N·m)</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <!-- ==================== Commands ==================== -->

    <!-- TransferItem -->
    <Command>
        <Identifier>TransferItem</Identifier>
        <DisplayName>转移</DisplayName>
        <Description>使用夹爪将物品从源位置转移到目标位置</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>SourcePosition</Identifier>
            <DisplayName>源位置</DisplayName>
            <Description>源位置</Description>
            <DataType>
                <DataTypeIdentifier>Position3D</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>TargetPosition</Identifier>
            <DisplayName>目标位置</DisplayName>
            <Description>目标位置</Description>
            <DataType>
                <DataTypeIdentifier>Position3D</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>GripperParam</Identifier>
            <DisplayName>夹爪参数</DisplayName>
            <Description>夹爪参数</Description>
            <DataType>
                <DataTypeIdentifier>GripperParam</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>ReleaseAfterFinish</Identifier>
            <DisplayName>结束是否松夹爪</DisplayName>
            <Description>结束是否松夹爪</Description>
            <DataType><Basic>Boolean</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

</Feature>
```

## 附录A.6：LidHandling（LidHandling_v1.0.sila.xml）

```xml
<?xml version="1.0" encoding="utf-8"?>
<Feature xmlns="http://www.sila-standard.org" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" Category="application" FeatureVersion="1.0" Originator="com.pharmablock" MaturityLevel="Draft" SiLA2Version="2.0">

    <!-- ============================================================ -->
    <!-- Feature: LidHandling 容器开关盖模块 -->
    <!-- ============================================================ -->
    <Identifier>LidHandling</Identifier>
    <DisplayName>容器开关盖模块</DisplayName>
    <Description>提供容器开盖和关盖操作。所有坐标为逻辑坐标系，Server自动选择夹爪Z轴。</Description>

    <!-- ==================== DataTypes ==================== -->
    <DataTypeDefinition>
        <Identifier>CommandResult</Identifier>
        <DisplayName>统一返回结构体</DisplayName>
        <Description>统一返回结构体</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Success</Identifier>
                    <DisplayName>执行结果</DisplayName>
                    <Description>执行结果</Description>
                    <DataType><Basic>Boolean</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Message</Identifier>
                    <DisplayName>描述信息</DisplayName>
                    <Description>描述信息</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Data</Identifier>
                    <DisplayName>扩展数据</DisplayName>
                    <Description>扩展数据</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <DataTypeDefinition>
        <Identifier>Position3D</Identifier>
        <DisplayName>逻辑坐标</DisplayName>
        <Description>逻辑坐标系中的三维坐标，单位mm</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>X</Identifier>
                    <DisplayName>X坐标</DisplayName>
                    <Description>X坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Y</Identifier>
                    <DisplayName>Y坐标</DisplayName>
                    <Description>Y坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Z</Identifier>
                    <DisplayName>Z坐标</DisplayName>
                    <Description>Z坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <DataTypeDefinition>
        <Identifier>GripperParam</Identifier>
        <DisplayName>夹爪参数</DisplayName>
        <Description>夹爪参数</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Position</Identifier>
                    <DisplayName>夹爪宽度(mm)</DisplayName>
                    <Description>夹爪宽度(mm)</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Force</Identifier>
                    <DisplayName>夹持力矩(N·m)</DisplayName>
                    <Description>夹持力矩(N·m)</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <!-- ==================== Commands ==================== -->

    <!-- ToggleLid -->
    <Command>
        <Identifier>ToggleLid</Identifier>
        <DisplayName>开关盖</DisplayName>
        <Description>mode=open时执行开盖流程（夹紧瓶身→旋开→放盖），mode=close时执行关盖流程（取盖→旋紧→释放），关盖位置复用OpenPosition</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Mode</Identifier>
            <DisplayName>操作模式</DisplayName>
            <Description>操作模式：open=开盖，close=关盖</Description>
            <DataType><Basic>String</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>ContainerDiameter</Identifier>
            <DisplayName>容器直径(mm)</DisplayName>
            <Description>容器直径(mm)，操作前用于夹紧瓶身（挤压行程）</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>OpenPosition</Identifier>
            <DisplayName>操作位置</DisplayName>
            <Description>开盖/关盖操作位置（关盖时复用此位置）</Description>
            <DataType>
                <DataTypeIdentifier>Position3D</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>LidPlacePosition</Identifier>
            <DisplayName>放盖位置</DisplayName>
            <Description>盖子放置位置（仅开盖时使用）</Description>
            <DataType>
                <DataTypeIdentifier>Position3D</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>OpenGripperParam</Identifier>
            <DisplayName>开盖夹爪参数</DisplayName>
            <Description>开盖夹爪参数</Description>
            <DataType>
                <DataTypeIdentifier>GripperParam</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>CloseGripperParam</Identifier>
            <DisplayName>关盖夹爪参数</DisplayName>
            <Description>关盖夹爪参数</Description>
            <DataType>
                <DataTypeIdentifier>GripperParam</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>RotationCycles</Identifier>
            <DisplayName>旋转圈数</DisplayName>
            <Description>旋转圈数</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>RotationSpeed</Identifier>
            <DisplayName>旋转速度(rpm)</DisplayName>
            <Description>旋转速度(rpm)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>RotationForce</Identifier>
            <DisplayName>旋转力矩(N·m)</DisplayName>
            <Description>旋转力矩(N·m)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>ZLiftHeight</Identifier>
            <DisplayName>Z抬升高度(mm)</DisplayName>
            <Description>Z抬升高度(mm)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

</Feature>
```

## 附录A.7：LiquidHandling（LiquidHandling_v1.0.sila.xml）

```xml
<?xml version="1.0" encoding="utf-8"?>
<Feature xmlns="http://www.sila-standard.org" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" Category="application" FeatureVersion="1.0" Originator="com.pharmablock" MaturityLevel="Draft" SiLA2Version="2.0">

    <!-- ============================================================ -->
    <!-- Feature: LiquidHandling 分液模块 -->
    <!-- ============================================================ -->
    <Identifier>LiquidHandling</Identifier>
    <DisplayName>分液模块</DisplayName>
    <Description>提供移液Tip头安装/退出、吸液、排液功能。所有坐标为逻辑坐标系，Server自动选择移液Z轴。</Description>

    <!-- ==================== DataTypes ==================== -->
    <DataTypeDefinition>
        <Identifier>CommandResult</Identifier>
        <DisplayName>统一返回结构体</DisplayName>
        <Description>统一返回结构体</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Success</Identifier>
                    <DisplayName>执行结果</DisplayName>
                    <Description>执行结果</Description>
                    <DataType><Basic>Boolean</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Message</Identifier>
                    <DisplayName>描述信息</DisplayName>
                    <Description>描述信息</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Data</Identifier>
                    <DisplayName>扩展数据</DisplayName>
                    <Description>扩展数据</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <DataTypeDefinition>
        <Identifier>Position3D</Identifier>
        <DisplayName>逻辑坐标</DisplayName>
        <Description>逻辑坐标系中的三维坐标，单位mm</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>X</Identifier>
                    <DisplayName>X坐标</DisplayName>
                    <Description>X坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Y</Identifier>
                    <DisplayName>Y坐标</DisplayName>
                    <Description>Y坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Z</Identifier>
                    <DisplayName>Z坐标</DisplayName>
                    <Description>Z坐标</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <!-- ==================== Commands ==================== -->

    <!-- AttachTip -->
    <Command>
        <Identifier>AttachTip</Identifier>
        <DisplayName>安装Tip头</DisplayName>
        <Description>安装Tip头到移液轴</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>TipPosition</Identifier>
            <DisplayName>Tip位置</DisplayName>
            <Description>Tip位置</Description>
            <DataType>
                <DataTypeIdentifier>Position3D</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>PressForce</Identifier>
            <DisplayName>压装力(N)</DisplayName>
            <Description>压装力(N)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- Aspirate -->
    <Command>
        <Identifier>Aspirate</Identifier>
        <DisplayName>吸液</DisplayName>
        <Description>从指定位置吸取液体</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>TargetPosition</Identifier>
            <DisplayName>吸液位置</DisplayName>
            <Description>吸液位置</Description>
            <DataType>
                <DataTypeIdentifier>Position3D</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>Volume</Identifier>
            <DisplayName>吸液体积(μL)</DisplayName>
            <Description>吸液体积(μL)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>AspirateSpeed</Identifier>
            <DisplayName>吸液速度(μL/s)</DisplayName>
            <Description>吸液速度(μL/s)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>ImmersionDepth</Identifier>
            <DisplayName>浸入深度(mm)</DisplayName>
            <Description>浸入深度(mm)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- Dispense -->
    <Command>
        <Identifier>Dispense</Identifier>
        <DisplayName>排液</DisplayName>
        <Description>将液体排到指定位置</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>TargetPosition</Identifier>
            <DisplayName>排液位置</DisplayName>
            <Description>排液位置</Description>
            <DataType>
                <DataTypeIdentifier>Position3D</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>Volume</Identifier>
            <DisplayName>排液体积(μL)</DisplayName>
            <Description>排液体积(μL)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>DispenseSpeed</Identifier>
            <DisplayName>排液速度(μL/s)</DisplayName>
            <Description>排液速度(μL/s)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>ImmersionDepth</Identifier>
            <DisplayName>浸入深度(mm)</DisplayName>
            <Description>浸入深度(mm)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- EjectTip -->
    <Command>
        <Identifier>EjectTip</Identifier>
        <DisplayName>退Tip头</DisplayName>
        <Description>退出使用后的Tip头</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>EjectPosition</Identifier>
            <DisplayName>退Tip位置</DisplayName>
            <Description>退Tip位置</Description>
            <DataType>
                <DataTypeIdentifier>Position3D</DataTypeIdentifier>
            </DataType>
        </Parameter>
        <Parameter>
            <Identifier>EjectForce</Identifier>
            <DisplayName>退Tip力(N)</DisplayName>
            <Description>退Tip力(N)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

</Feature>
```

## 附录A.8：Debug（Debug_v1.0.sila.xml）

```xml
<?xml version="1.0" encoding="utf-8"?>
<Feature xmlns="http://www.sila-standard.org" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" Category="application" FeatureVersion="1.0" Originator="com.pharmablock" MaturityLevel="Draft" SiLA2Version="2.0">

    <!-- ============================================================ -->
    <!-- Feature: Debug 调试模式 -->
    <!-- ============================================================ -->
    <Identifier>Debug</Identifier>
    <DisplayName>调试模式</DisplayName>
    <Description>调试模式功能集合，包含夹爪调试、轴单步调试、LED控制、移液器调试等功能</Description>

    <!-- ==================== DataTypes ==================== -->
    <DataTypeDefinition>
        <Identifier>CommandResult</Identifier>
        <DisplayName>统一返回结构体</DisplayName>
        <Description>统一返回结构体</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Success</Identifier>
                    <DisplayName>执行结果</DisplayName>
                    <Description>执行结果</Description>
                    <DataType><Basic>Boolean</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Message</Identifier>
                    <DisplayName>描述信息</DisplayName>
                    <Description>描述信息</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Data</Identifier>
                    <DisplayName>扩展数据</DisplayName>
                    <Description>扩展数据</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <!-- ==================== 夹爪调试 ==================== -->
    <!-- GripperTest -->
    <Command>
        <Identifier>GripperTest</Identifier>
        <DisplayName>夹爪夹紧</DisplayName>
        <Description>以指定速度、力矩将夹爪夹紧至指定位置</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Speed</Identifier>
            <DisplayName>开合速度(mm/s)</DisplayName>
            <Description>开合速度(mm/s)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Position</Identifier>
            <DisplayName>张开宽度(mm)</DisplayName>
            <Description>张开宽度(mm)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Force</Identifier>
            <DisplayName>夹持力矩(N·m)</DisplayName>
            <Description>夹持力矩(N·m)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- GripperRotate -->
    <Command>
        <Identifier>GripperRotate</Identifier>
        <DisplayName>夹爪旋转</DisplayName>
        <Description>以指定速度、力矩旋转夹爪至指定角度</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Speed</Identifier>
            <DisplayName>旋转速度(rpm)</DisplayName>
            <Description>旋转速度(rpm)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Position</Identifier>
            <DisplayName>旋转角度(°)</DisplayName>
            <Description>旋转角度(°)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Force</Identifier>
            <DisplayName>旋转力矩(N·m)</DisplayName>
            <Description>旋转力矩(N·m)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- ==================== 轴单步调试 ==================== -->

    <!-- AxisStepMove -->
    <Command>
        <Identifier>AxisStepMove</Identifier>
        <DisplayName>轴单步移动</DisplayName>
        <Description>指定轴以指定速度单步移动到目标位置，axis取值：x / y / powder_z / liquid_z / gripper_z</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Axis</Identifier>
            <DisplayName>轴标识</DisplayName>
            <Description>轴标识</Description>
            <DataType><Basic>String</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Speed</Identifier>
            <DisplayName>运动速度(mm/s)</DisplayName>
            <Description>运动速度(mm/s)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Position</Identifier>
            <DisplayName>目标位置(mm)</DisplayName>
            <Description>目标位置(mm)</Description>
            <DataType><Basic>Real</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- ==================== LED ==================== -->

    <!-- LedOn -->
    <Command>
        <Identifier>LedOn</Identifier>
        <DisplayName>LED开</DisplayName>
        <Description>打开指定索引的LED</Description>
        <Observable>No</Observable>
        <Parameter>
            <Identifier>Index</Identifier>
            <DisplayName>LED索引</DisplayName>
            <Description>LED索引</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- LedOff -->
    <Command>
        <Identifier>LedOff</Identifier>
        <DisplayName>LED关</DisplayName>
        <Description>关闭指定索引的LED</Description>
        <Observable>No</Observable>
        <Parameter>
            <Identifier>Index</Identifier>
            <DisplayName>LED索引</DisplayName>
            <Description>LED索引</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- ==================== 移液器 ==================== -->

    <!-- PipettorHome -->
    <Command>
        <Identifier>PipettorHome</Identifier>
        <DisplayName>移液器归零</DisplayName>
        <Description>移液器回零点</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>执行结果</DisplayName>
            <Description>执行结果</Description>
            <DataType>
                <DataTypeIdentifier>CommandResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

    <!-- ==================== Properties ==================== -->

    <!-- Pipettor Pressure Property -->
    <Property>
        <Identifier>PipettorPressure</Identifier>
        <DisplayName>移液器气压</DisplayName>
        <Description>移液器当前气压(kPa)</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Real</Basic></DataType>
    </Property>

    <!-- Pipettor Work State Property -->
    <Property>
        <Identifier>PipettorWorkState</Identifier>
        <DisplayName>移液器工作状态</DisplayName>
        <Description>0-空闲, 1-工作, 99-故障</Description>
        <Observable>Yes</Observable>
        <DataType><Basic>Integer</Basic></DataType>
    </Property>

</Feature>
```

## 附录A.9：Vision（Vision_v1.0.sila.xml）

```xml
<?xml version="1.0" encoding="utf-8"?>
<Feature xmlns="http://www.sila-standard.org" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" Category="application" FeatureVersion="1.0" Originator="com.pharmablock" MaturityLevel="Draft" SiLA2Version="2.0">

    <!-- ============================================================ -->
    <!-- Feature: Vision 视觉模块 -->
    <!-- ============================================================ -->
    <Identifier>Vision</Identifier>
    <DisplayName>视觉模块</DisplayName>
    <Description>提供板位视觉识别能力，返回各板位的板类型、置信度、包围盒与中心点。图像 base64 经 FDL 传输，Server 应控制原图在 3MB 以内（gRPC 消息默认上限 4MB）</Description>

    <!-- ==================== DataTypes ==================== -->
    <DataTypeDefinition>
        <Identifier>PlateDetectItem</Identifier>
        <DisplayName>板检测项</DisplayName>
        <Description>单个板位的识别结果</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Station</Identifier>
                    <DisplayName>板位编号</DisplayName>
                    <Description>板位编号</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>PlateType</Identifier>
                    <DisplayName>板类型</DisplayName>
                    <Description>如 96-well-plate、24-well-plate、12-well-plate、96-Thermo-Tube；空字符串表示未检出</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Score</Identifier>
                    <DisplayName>置信度(0~1)</DisplayName>
                    <Description>置信度(0~1)</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Box</Identifier>
                    <DisplayName>包围盒[x1,y1,x2,y2]</DisplayName>
                    <Description>图像像素坐标，未检出时为空列表</Description>
                    <DataType>
                        <List>
                            <DataType><Basic>Real</Basic></DataType>
                        </List>
                    </DataType>
                </Element>
                <Element>
                    <Identifier>Center</Identifier>
                    <DisplayName>中心点[x,y]</DisplayName>
                    <Description>图像像素坐标，未检出时为空列表</Description>
                    <DataType>
                        <List>
                            <DataType><Basic>Real</Basic></DataType>
                        </List>
                    </DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <DataTypeDefinition>
        <Identifier>PlateRecognitionResult</Identifier>
        <DisplayName>板位识别结果</DisplayName>
        <Description>板位识别结果</Description>
        <DataType>
            <Structure>
                <Element>
                    <Identifier>Code</Identifier>
                    <DisplayName>返回码(0成功)</DisplayName>
                    <Description>返回码(0成功)</Description>
                    <DataType><Basic>Integer</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>Msg</Identifier>
                    <DisplayName>返回消息</DisplayName>
                    <Description>返回消息</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>CostMs</Identifier>
                    <DisplayName>识别耗时(ms)</DisplayName>
                    <Description>识别耗时(ms)</Description>
                    <DataType><Basic>Real</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>ImageBase64</Identifier>
                    <DisplayName>识别图像(base64)</DisplayName>
                    <Description>可为空字符串</Description>
                    <DataType><Basic>String</Basic></DataType>
                </Element>
                <Element>
                    <Identifier>DetectList</Identifier>
                    <DisplayName>检测结果列表</DisplayName>
                    <Description>检测结果列表</Description>
                    <DataType>
                        <List>
                            <DataType>
                                <DataTypeIdentifier>PlateDetectItem</DataTypeIdentifier>
                            </DataType>
                        </List>
                    </DataType>
                </Element>
            </Structure>
        </DataType>
    </DataTypeDefinition>

    <!-- ==================== Commands ==================== -->

    <!-- PlateRecognize -->
    <Command>
        <Identifier>PlateRecognize</Identifier>
        <DisplayName>板位识别</DisplayName>
        <Description>对工作站所有板位执行一次视觉识别，返回各板位的板类型、置信度、包围盒与中心点</Description>
        <Observable>Yes</Observable>
        <Parameter>
            <Identifier>Timeout</Identifier>
            <DisplayName>超时时间(s)</DisplayName>
            <Description>命令执行超时时间，单位秒，缺省10</Description>
            <DataType><Basic>Integer</Basic></DataType>
        </Parameter>
        <Response>
            <Identifier>Result</Identifier>
            <DisplayName>识别结果</DisplayName>
            <Description>识别结果</Description>
            <DataType>
                <DataTypeIdentifier>PlateRecognitionResult</DataTypeIdentifier>
            </DataType>
        </Response>
    </Command>

</Feature>
```
