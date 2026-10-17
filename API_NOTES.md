# GenLayer API 实测笔记

所有结论均来自 Stable Studionet 上的真实部署与交易，非文档推断。
GenVM: v0.2.16-x86_64-linux-release | Chain ID 61999

## 已确认存在

| 接口 | 实测证据 |
|---|---|
| gl.nondet.web.get / head / post / patch / delete / request / render | b_web_get OK |
| gl.nondet.exec_prompt(response_format='json') | c_llm OK |
| gl.vm.run_nondet_unsafe / run_nondet | c_llm / d_error |
| gl.vm.Return / UserError / VMError / Result / ResultCode | dir(gl.vm) |
| gl.eq_principle.strict_eq / prompt_comparative / prompt_non_comparative | dir(gl.eq_principle) |
| gl.storage.TreeMap / DynArray / allow_storage / copy_to_memory / inmem_allocate | dir(gl.storage) |
| gl.get_contract_at / deploy_contract / contract_interface | dir(gl) |
| gl.message.sender_address / contract_address / chain_id / origin_address / value / count / index | dir(gl.message) |

## 与官方文档不一致（以实测为准）

1. gl.UserError 不存在 -> 用 gl.vm.UserError
2. 非确定性块内可以读 storage 标量字段（文档称不可访问）；容器类型仍建议 copy_to_memory
3. strict_eq 内不强制需要 web 调用，纯 Python 函数亦可
4. web-access 页只写 request，实际 get/head/post/patch/delete/render 均存在

## 行为语义

- run_nondet_unsafe 在 leader 抛 UserError 且 validator 接受时，会把该 UserError 抛给调用方；
  调用方需 try/except 才能避免整笔交易 revert
- 只比较决策字段、不比较自由文本，可稳定收敛

## 硬约束

- gl.message 无时间戳、无区块号
  -> 新鲜度改用 epoch 计数器；展示用时间取 HTTP Date 头并截断到 10 分钟窗口
- 存储字段必须在 class body 声明并带类型；list->DynArray, dict->TreeMap, int->u256/i32/bigint
- 副作用（storage 写、gl.get_contract_at、emit）必须在非确定性块之外
- 文件第一行必须是 runner comment，且引号必须是直引号（弯引号会导致 invalid_contract absent_runner_comment）

## 证据

探针合约 0xC26EbA182901005e9538819E1c58de513F812254
- b_web_get 0x0987f29c74bf733fe3421ff4672277043b121184d949161a2ee5c4a09f16e648
- c_llm     0x4a8ed03cd4dfa64e45694756e071a7fd0b9b96e34e09640b206d579d0e1c5a05
- d_error   0x23e74c0b92ec9623e5d564d9a752f4a8af1d3036e2d1be2935a12a4597345831
- e_boundary 0xeb1b1d547e84c996e9694ab72a96a153c8edd90cb14ce139b412b918fc48c716

## 已确认存在（第二轮）

| 接口 | 证据 |
|---|---|
| TreeMap[str,str] set/read | t1_storage |
| DynArray[str] append/len/iterate | t1_storage |
| u256 算术 (self.n + u256(1)) | t1_storage |
| Address 存储字段 + Address(str) 构造 | t1_storage / t2_set_target |
| gl.get_contract_at(addr).view().method() 跨合约同步读 | t3_cross_view |
| gl.storage.copy_to_memory 可用于 dataclass | 见 S2 实现 |

## 证据

probe3 合约 0xF00ad386EdB142EbFCe4124ae98e6c9B65651468
target 合约 0xEF9cCfa73Cf4BF834Fd840C0901be7fC31888F72
- t1 0x83df95fdec912a0a3f906d1a46935d0b0393f0778903b88196b302c656d6ae26
- t2 0x0e672e44a87df4f183da725b4cb328dff2b63f3f52f6b9d729b69806bd83387b
- t3 0xb70feb9677076a94105f12c47db184d3e450854dedefd54e4e5c5d731534ea29

## 硬约束（已踩坑）

- 文件第 1 行（runner comment）之后**不要再放注释块**。
  第 2 行若是单独的 `#`，GenVM 解析 runner comment 会失败，
  报 invalid_contract 或 absent_runner_comment。
  正确写法：第 1 行 runner comment -> 空行 -> import。
  验证：8 个带顶部注释块的文件全部失败，7 个不带的全通过。
- 类内部的注释（含中文、长横线）是安全的。
- 引号必须是直引号；从网页粘贴后要检查。
---

## S3 离线测试环境硬约束（Windows）

以下每条都是实测踩坑后固化。改动前先读。

### 1. 合约第 1 行必须是 runner comment，其后不得有注释块
- 第 1 行：`# { "Depends": "py-genlayer:<hash>" }`
- 第 2 行空行，第 3 行起 `import`。若第 2 行是单独的 `#`，GenVM 解析 runner comment 失败，报 `invalid_contract`。
- 统计验证：8 个带顶部注释块的文件全失败，7 个不带的全部通过，零例外。
- 类内部注释（含中文、长横线）安全，不影响解析。

### 2. 引号必须是 ASCII 直引号
中文输入法会把 `"` 打成弯引号，runner comment 里必须是 `"`。

### 3. GlTest 直连模式的 GenVM SDK 下载会 404（上游未修）
- `gltest/direct/sdk_loader.py` 解析 `releases/latest` 得到 `v0.3.0-rc7`，然后只按资产名 `genvm-universal.tar.xz` 找。
- v0.3.0-rc7 起该资产已改名 `genvm-runners-all.tar.xz`（内部结构兼容），故 404。10 个测试各自重试下载，累计 337s 全失败。
- 解法：手动预置缓存。缓存优先级高于联网解析。
- 缓存目录：`%USERPROFILE%\.cache\gltest-direct`（本机用 junction 指向 `F:\genlayer\gltest-cache`）
- 期望文件名：`genvm-universal-<version>.tar.xz`，内容放 `genvm-runners-all.tar.xz` 即可
- 首次仍需解压 xz（约 13s），之后全走缓存

### 4. Windows 上 fd0 注入收尾会 PermissionError（上游未修）
- `gltest/direct/loader.py::_inject_message_to_fd0` 在 `os.dup2(fd, 0)` 后立刻 `os.unlink(path)`；Windows 不允许删仍被占用的文件 → `PermissionError [WinError 32]`。
- 修复脚本：`scripts/patch_gltest_windows.py`（把 unlink 包进 try/except OSError）
- 该脚本改的是 site-packages，`pip install -U genlayer-test` 后必须重跑

### 5. mock_web / mock_llm 是「注册顺序 + 首个命中生效」
- 两个方法只 append 不覆盖。同 pattern 二次注册无效，旧规则永远先命中。
- 覆盖已注册 URL 必须 `clear_mocks()` 后全量重注册，或把 `_setup` 参数化。
- 需要按来源区分 LLM 时，用匹配页面内容的 pattern，且**必须注册在兜底 `r".*"` 之前**。
- 未命中任何 mock 抛 `MockNotFoundError`，不静默降级。

### 6. 环境固定
- Python 3.13.16（3.15.0 上 ckzg 无 cp315 wheel，本机无 C++ 编译器装不上）
- genlayer-test 0.29.2
- 所有命令用 `py -3.13` 前缀
- cmd 里 Ctrl+C 是中断，不是复制

### 7. 环境复现命令
```cmd
mkdir F:\genlayer\gltest-cache
mkdir "%USERPROFILE%\.cache"
mklink /J "%USERPROFILE%\.cache\gltest-direct" "F:\genlayer\gltest-cache"
curl -L --retry 3 -o "F:\genlayer\gltest-cache\genvm-universal-v0.3.0-rc7.tar.xz" ^
  https://github.com/genlayerlabs/genvm/releases/download/v0.3.0-rc7/genvm-runners-all.tar.xz
py -3.13 scripts\patch_gltest_windows.py
py -3.13 -m pytest tests/direct -v