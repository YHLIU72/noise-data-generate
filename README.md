# HVAC Aeroacoustic ROM

纯 Python、无运行时第三方依赖的汽车 HVAC 气动声学降阶数据生成引擎。它把结构参数和运行工况映射为一组可复现的参数化数值模拟结果：风量/压降工作点、BPF 及不等距叶片边频、宽带声源 PSD、受限的声学传播，以及由同一 PSD 推导出的窄带、1/3 倍频程、OASPL 和 A 计权 OASPL。

## 先说明数据口径

本项目生成的是 `parameterized_numerical_simulation`，不是实测数据，也不是 CFD/CAA 高保真结果。默认输出的绝对声压级使用显式的、尚未针对某一台架或具体产品标定的降阶压力系数。代码会在 `provenance.json` 和每个模拟结果中写入：

```json
{
  "data_kind": "parameterized_numerical_simulation",
  "experimental_data": false,
  "cfd_or_caa_solver": false,
  "calibrated_against_experiment": false
}
```

因此，结果可以用于受控算法实验、频率迁移测试、采样策略和模型结构验证；在得到明确的实验/公开基准数据并完成标定之前，不能写成“实测声学性能”或“已验证的真实产品噪声”。

## 模型链

1. 空气状态：由温度和环境压力计算密度、声速。
2. 气动工作点：用风机曲线和系统阻力曲线求解 `fan_pressure(Q) = system_pressure(Q)`。
3. 周期声源：由转速和叶片数确定 `f_BPF = ZN/60`；叶片角位置的离散傅里叶系数决定 BPF 倍频及不等距叶片边频的相对能量。
4. 宽带声源：由平均速度、湍流强度和积分长度尺度确定源方差和转折频率，使用具有高频衰减的 von-Kármán-like 形状构造 PSD。
5. 声学传播：使用均匀等效风道的平面波传递模型，叠加距离扩散、热黏性损失和等效芯体衰减。
6. 后处理：所有窄带、1/3 倍频程、OASPL 和 A 计权结果都从同一个一侧 PSD 积分得到，单位明确为 `Pa²/Hz`、`Pa²` 和 `dB re 20 µPa`。

主要方程的降阶形式为：

```text
U_tip = pi D2 N / 60
p_fan(Q) = p_shut [1 - (Q/Q_free)^2]
p_sys(Q) = 0.5 rho K (Q/A)^2

theta_i = 2 pi i/Z + beta/Z sin(2 pi m i/Z)
C_k = (1/Z) sum_i exp(-j k theta_i)

S_t(f) = sum_k E_k G(f; f_k, sigma_k)
S_b(f) = p_b,rms^2 * g(f) / integral[g(f) df]
S_pp(f) = |H(f)|^2 [S_t(f) + S_b(f)]
```

这里的压力系数、阻力系数和等效衰减参数是模型配置中的可追溯建模假设，不应被解释为某一真实 HVAC 型号的已测参数。

## 声学传播有效性

传播模块根据等效圆形风道直径估计首个横向模态截止频率：

```text
f_cutoff ≈ 1.84 c / (pi D_eq)
f_valid_max = plane_wave_margin * f_cutoff
```

默认 `plane_wave_margin=0.70`。当请求频率上限超过该范围时，程序默认直接报错，避免把未解析的模态/反射效应悄悄当成有效结果。只有显式传入 `allow_out_of_validity=True` 或 CLI 的 `--allow-out-of-validity` 才会继续计算；此时结果会带有警告，且 `validity_within_limit=false`。

该传播模型不是 FEM/BEM、不是多模态传递矩阵求解，也不代表完整 HVAC 箱体、芯体和风门阻抗。

## 安装与运行

运行时不需要 NumPy、SciPy、Fluent 或 COMSOL。Python 3.10+ 即可。

直接运行一个 8 工况批次：

```powershell
$env:PYTHONPATH = "src"
python -m hvac_aeroacoustic_rom.cli --output outputs\demo --samples 8 --seed 20261126
```

生成：

- `metadata.csv`：每个工况一行，包含结构、工作点、OASPL、有效性和警告。
- `spectra.csv`：每个工况的 `frequency_hz`、一侧 `psd_pa2_per_hz`、窄带声压级和 A 计权窄带声压级。
- `octave_bands.csv`：由同一 PSD 积分得到的 1/3 倍频程能量和声压级。
- `provenance.json`：引擎版本、配置、数据性质、模型范围和每个工况的有效性记录。

也可以用 Python API：

```python
from pathlib import Path

from hvac_aeroacoustic_rom import (
    ModelConfig,
    default_parameter_specs,
    generate_batch,
    latin_hypercube,
    simulate_case,
)

single = simulate_case(config=ModelConfig(frequency_max_hz=900.0))
print(single.operating.flow_m3_s, single.oaspl_db, single.a_weighted_oaspl_db)

samples = latin_hypercube(default_parameter_specs(), n_samples=32, seed=7)
generate_batch(samples, Path("outputs/batch"), ModelConfig(frequency_max_hz=900.0))
```

自定义采样空间时，传入 JSON 文件：

```json
{
  "rpm": {"low": 1800, "high": 3600},
  "blade_count": {"values": [35, 39, 43], "kind": "int"},
  "tongue_gap_ratio": {"low": 0.06, "high": 0.10}
}
```

```powershell
$env:PYTHONPATH = "src"
python -m hvac_aeroacoustic_rom.cli --output outputs\custom --samples 20 --ranges-json ranges.json
```

## 标定与验证建议

要把结果用于绝对噪声预测，应至少建立一个版本化的参考数据表，并明确：风机/箱体型号、传声器位置、转速、流量或压降、频率分辨率、窗函数和测量环境。建议按以下顺序标定：

1. 用风机性能图拟合工作点模型的自由流量、关断压力和阻力系数。
2. 用同步阶次/窄带数据拟合 `tonal_pressure_coefficient` 以及不同阶次的衰减。
3. 用宽带 PSD 或壁面压力谱数据拟合 `broadband_pressure_coefficient`、湍流强度和积分长度尺度。
4. 用传递函数或插入损失数据拟合芯体/风道的等效衰减。
5. 按结构或产品分组留出独立工况，报告 OASPL、A 计权 OASPL、峰值频率误差、频带误差和不确定度。

在完成这些步骤前，README、论文或数据集说明都应保留 `experimental_data=false`，并将模型输出称为“参数化数值模拟数据”或“虚拟试验数据”。

## 测试

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

测试覆盖：工作点压力平衡、PSD 与 OASPL 一致性、1/3 倍频程能量覆盖、BPF 随转速/叶片数迁移、不等距叶片边频、传播有效性拒绝、采样可复现性、批量文件和 provenance 配对。

## 目录

```text
src/hvac_aeroacoustic_rom/
  models.py             输入/输出数据结构与有效性记录
  operating_point.py    风机曲线、系统阻力和工作点求解
  sources.py            BPF/边频与宽带源 PSD
  propagation.py        平面波传播和有效性限制
  spectrum.py           PSD、A 计权、1/3 倍频程、OASPL
  sampling.py           无依赖拉丁超立方采样
  validation.py         内部一致性审查
  engine.py             单工况/批量 API 和输出文件
  cli.py                命令行入口
tests/
  test_engine.py
```
