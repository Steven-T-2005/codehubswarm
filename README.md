# codehubswarm
一、DFR是什么

Openharymony DFR(Design For Reliability) 可靠性设计，在产品运行期间确保全面满足用户的运行要求，包括减少故障发生，降低故障发生的影响，故障发生后能尽快恢复。

DFR中，故障检测是故障管理的基础，是故障分析、定位、恢复、质量度量的前提。故障检测是否准确，故障特征日志是否清晰完备，很大程度上决定了产品的开发效率和交付成本，严重影响产品质量和体验。故障种类异常繁多，产品和软件业务不同，故障的原因和表现也千差万别，分析定位疑难问题是对工程师经验、能力、智慧的多重考验。

       一般地，我们将故障分成系统基础故障和业务故障。系统基础故障是系统及各业务均会产生的公共类型的故障，业务故障则是具体业务特有的故障。Openharmony提供了统一的故障检测框架FaultDetector，对于系统基础故障，FaultDetector提供了精准的故障检测器，并生成清晰完备的故障特征日志。对于业务功能故障，则结合业务功能设计进行检测。

基础故障检测器包括：整机重启及子系统异常、进程崩溃、死机冻屏、不开机、资源泄漏、地址越界六类。故障检测器检测的详细故障类型如下表所示：

故障检测器

	

模块名称

	

故障类型




进程崩溃检测器

	

Faultlogger

	

CPP Crash、JS Crash




死机冻屏检测器

	

FreezeDetector

	

App Freeze、Systerm Freeze




整机重启检测器

	

BBOX

	

System Reset、Subsystem Crash，Hardware Fault




不开机故障检测器

	

BootDetector

	

Boot Failed




资源泄露检测器

	

LeakDetecotor

	

MemoryLeak，ThreadLeak，FD Leak




地址越界检测器

	

MemCollector

	

KSAN、ASAN

二、DFR有什么
崩溃故障维测 Faultloggerd
死故障维测 FreeDetector
踩内存故障维测 MemDetector
资源泄露故障维测 LeakDetector
不开机维测 BootDetector
整机重启维测  BBOX
2.1 崩溃故障日志收集模块（Faultloggerd）

Openharmony Faultloggerd是系统级的原生（C/C++）运行时崩溃临时日志的生成及管理模块。进程崩溃时，开发者可以在预设的路径下找到故障日志，定位相关问题（hap默认生成混合栈（JS/C++））。

2.1.1 崩溃异常信号

目前主要支持对以下C/C++运行时崩溃异常信号的处理：

信号值	信号	解释	触发原因
4	SIGILL	非法指令	执行了非法指令，通常是因为可执行文件本身出现错误，或者试图执行数据段，堆栈溢出时也有可能产生这个信号。
5	SIGTRAP	断点或陷阱异常	由断点指令或其它trap指令产生。
6	SIGABRT	abort发出的信号	调用abort函数生成的信号。
7	SIGBUS	非法内存访问	非法地址，包括内存地址对齐（alignment）出错。比如访问一个四个字长的整数，但其地址不是4的倍数。它与SIGSEGV的区别在于后者是由于对合法存储地址的非法访问触发的（如访问不属于自己存储空间或只读存储空间）。
8	SIGFPE	浮点异常	在发生致命的算术运算错误时发出，不仅包括浮点运算错误，还包括溢出及除数为0等其它所有的算术的错误。
11	SIGSEGV	无效内存访问	试图访问未分配给自己的内存，或试图往没有写权限的内存地址写数据。
16	SIGSTKFLT	栈溢出	堆栈溢出。
31	SIGSYS	系统调用异常	非法的系统调用。

进程因上述异常信号崩溃将会在设备 /data/log/faultlog/temp 目录下生成完整的崩溃日志，可基于该崩溃日志进行问题定位可分析。

崩溃日志介绍和和常见问题指南参考: https://gitee.com/openharmony/hiviewdfx_faultloggerd/blob/master/docs/usage.md

2.1.2 故障订阅：

应用可以通过故障订阅方式，获取崩溃事件和日志，/data/log/faultlog/faultlogger 生成日志

https://gitee.com/openharmony/docs/blob/master/zh-cn/application-dev/dfx/hiappevent-watcher-crash-events-arkts.md

2.1.3 Faultloggerd框架结构

  Faultloggerd各子模块介绍如下：

（1）SignalHandler：信号处理器，接收系统异常信号，触发抓取进程异常时的现场信息。

（2）DumpCatcher：堆栈信息抓取工具库，提供了抓取指定进程和线程的堆栈信息的能力。

（3）FaultloggerdClient：崩溃临时日志管理客户端，接收申请文件描述符、堆栈导出等请求。

（4）ProcessDump：进程信息抓取二进制工具，通过命令行方式提供抓取指定进程、线程堆栈信息的能力。

（5）crasher：崩溃构造器，提供了崩溃构造和模拟能力。

（6）FaultloggerdServer：核心服务处理模块，接收并处理客户端的请求。

（7）FaultloggerdSecure：权限校验模块，对运行时崩溃日志生成和抓取提供权限管理和校验能力。

（8）FaultloggerdConfig：崩溃临时日志管理模块。

Faultloggerd详细介绍和使用说明可参考：

https://gitee.com/openharmony/hiviewdfx_faultloggerd/blob/master/README_zh.md

2.2 卡死故障判断模块（FreeDetector）

应用卡死故障维测方案主要包括卡死故障检测、卡死故障判决两大部分，其中卡死故障检测包括系统检测点、应用检测点两大部分。同时利用故障日志生成、故障根因智能分析、故障日志内容管理、故障上报等模块，完成应用卡死故障的检测-判决-上报全流程。

2.2.1 FreezeDetector各个子模块功能介绍如下：

（1）Plugin模块：应用/系统卡死事件监听插件模块，负责实现插件化平台接口，注册监听应用/系统卡死事件，实现插件动态加载。

（2）WatchPoint模块：检测点模块，用于保存应用/系统卡死事件携带的上报信息。

（3）Rules模块：判决规则配置读取模块，用于读取故障判决规则配置文件/system/etc/hiview/freeze_rules.xml。

（4）Resolver模块：判决模块，根据判决规则时间窗口，检索DB，将符合判决规则的所有应用/系统卡死事件日志进行关联与合并。

（5）DBHelper模块：数据库检索模块，负责根据检索条件，找出数据库中匹配的应用/系统卡死事件。

（6）Vendor模块：厂商定制功能模块，负责实现卡死方案中闭源逻辑。

2.2.2 Appfreeze 现在提供的主要检测能力：
AppFreeze故障类型	需要匹配的事件	事件含义


LIFECYCLE_TIMEOUT

	

LIFECYCLE_TIMEOUT

	

ability生命周期切换超时




APP_LIFECYCLE_TIMEOUT

	

APP_LIFECYCLE_TIMEOUT

	

app生命周期切换超时




THREAD_BLOCK_6S

	

THREAD_BLOCK_6S && THREAD_BLOCK_3S

	

应用主线程卡死检测




UI_BLOCK_6S

	

UI_BLOCK_6S && UI_BLOCK_3S

	

UI卡死检测




APPLICATION_BLOCK_INPUT

	

APPLICATION_BLOCK_INPUT

	

ANR，输入响应超时




SCREEN_ON_TIMEOUT

	

SCREEN_ON_TIMEOUT

	

按下power键10s屏幕未亮




NO_DRAW

	

NO_DRAW

	

应用可见窗口绘制超时检测

检测基本原理可参考：

3 踩内存故障检测（MemDetector）

踩内存问题，比如buffer越界访问、使用已经释放的内存、重复释放等，一直都是使用C/C++语言进行编程开发所面对的痛点问题，尤其是写越界，难以抓取踩内存第一现场，解决难度大、解决周期长。

①严重影响体验：重启、死机、应用闪退、业务功能莫名异常

②定位困难：难以抓取踩内存第一现场，解决起来比较困难

③检测困难：场景复杂，难复现

OpenHarmony DFX的踩内存故障检测功能（MemDetector）完整集成了当前业界最优秀的检测工具AddressSanitizer/asan，可以检测栈和堆缓冲区上溢/下溢、释放之后的堆栈继续使用、超出范围的堆栈使用、重复释放等故障，并且通过工程化、定制化的改造，提升了易用性，在能力不降低的情况下，减轻对资源的消耗。

AddressSanitizer（ASan）是一个快速的内存错误检测工具。采用了CTI(CompileTime Instrumentation)技术，即在编译时进行代码插入，相比其他同类工具， 它运行速度非常快，只拖慢程序两倍左右。它包括一个编译器instrumentation模块和一个提供malloc()/free()替代项的运行时库。从gcc 4.8和LLVM3.1之后，AddressSanitizer已经分别成为两种编译器的一部分。

天网版本：针对系统和应用内存问题，构建的调试版本。

4 资源泄露故障检测（LeakDetector）

帮助开发者检测FD、Thread、内存等资源泄漏故障，提供定位所需基本信息。

泄漏类型	检测机制
句柄泄漏（FD_LEAK）	60s一次遍历进程，获取进程fd句柄总数，超过阈值（5000个）时抓取详细句柄信息，同步上报泄漏
线程泄漏（THREAD_LEAK）	60s一次遍历进程，获取进程的总线程数，超过阈值（700个）时抓取详细线程名信息，同步上报泄漏
内存泄漏（MEMORY_LEAK）	

js泄漏（JS_LEAK）

	

虚拟机内部进行插桩，当heap使用量超过85% 或者 触发OOM时会抓取heapdump，同步上报该故障




native内存泄漏（PSS_MEMORY）

	

以应用进程平均动态峰值内存作为基线，60s一次轮询监控，当动态内存峰值超过基线值2倍，判定泄漏，同时触发管控。


ashmem/ion/gpu等内存泄漏 （KERNEL_MEMORY）	基于ashmem/ion/gpu的基线值，超过基线值时会判定泄漏，同步抓取维测信息
4.4.1 线程泄露和fd泄露

线程和句柄对于进程来说是一种固定资源，如果不对其进行把控，使用结束不及时释放，会造成一系列稳定性异常。问题定为线程泄漏或者句柄泄漏之后，一定要确认你们是否真的需要或者会同时存在这么多活跃thread或者fd。

线程泄漏和fd泄漏，检测方式是：遍历进程，根据proc/[pid]/fd和/proc/[pid]/task获取的句柄或线程数，判断是否超过我们设定的阈值，如果超过，则打印当前该进程中现存活跃的线程或句柄。

4.4.2 内存泄露

内存泄漏按照泄漏点归属不同分为两种：用户态进程和内核节点。

a. NATIVE泄漏：用户态进程内存泄漏的判断标准，根据NEXT各应用领域申请的基线，对这个应用进行监控，如果在3个采样周期（2+分钟）内我们发现进程PSS一直大于PSS基线，才会判定泄漏。

b. JS泄漏：在虚拟机内部做插桩，当heap使用量超过85% 或者 触发OOM时会上报该故障。

c. 内核泄漏：内核节点内存泄漏的判断标准，根据/proc/meminfo下获取的资源使用量信息，如IonTotalUsed、CmaUsed、VmallocUsed、Slab、AshmemUsed，与基线进行判断，同样当超过基线时会进行监控，如果在8个采样周期（40分钟）内我们发现一直超过基线，则会判定为泄漏，打印/proc/下ion_process_info、slabinfo、cma_info、vmalloc_info、ashmem_process_info信息到日志。




5 不开机维测 （BootDetector）

单框架不开机涉及设备开机各个阶段，包括BootLoader阶段、kernel阶段、native阶段和应用阶段。

1. 开机dump阶段判断重启原因获取系统panic等异常。

2. BootLoader阶段主要是包括关键镜像故障，系统崩溃/卡死等故障。

3. Kernel阶段更多的是子系统启动异常。

4. Native阶段的主要是在init检测分区异常、数据损坏、系统/服务崩溃、卡死应用阶段通过APP和Ability生命周期上报的阶段判断

6 整机重启维测（BBOX）

Bbox全称为BlackBox，是OpenHarmony DFX提供的一个芯片维测框架，提供整机异常重启故障的上报框架和定位信息。

Bbox以解耦、单一、简洁为原则，提供统一接口，管理内核及各模块的异常信息和维测行为。在处理异常时，统一管理日志保存和模块恢复，提高日志保存的最大可能性；并统一记录复位原因，帮助设备侧开发者提升定位效率。

为了高效管理芯片维测，在OpenHarmony DFX中构建了芯片维测故障处理模型，对芯片故障事件进行了定义。简言之，任何一次故障事件都是有主体的，即跟某个模块相关联。当故障发生时，把与之关联的模块日志及内存信息保存下来，可提供有限而又足够的故障信息帮助开发者快速定位问题

故障事件是OpenHarmony DFX维测处理模型的核心，故障事件发生时，执行故障事件所在模块注册的回调函数进行日志保存及故障恢复动作。OpenHarmony DFX定义了一些默认芯片故障事件Event及对应Category分类，用于对故障信息进行管理，OEM厂商可自行基于Bbox扩展自己的故障事件，对自己的产品质量进行管理。

三、 DFR专有名词

CppCrash：C++/C运行时由于未处理的信号导致的故障

JsCrash：Js运行时未处理的错误导致的故障

AppFreeze：应用关键方法、关键线程执行超时导致的故障

AppCrash：应用进程崩溃，目前包含CppCrash和JsCrash两类

SystemFreeze: 系统单进程、多进程间调用超时导致的故障

SystemError: 系统进程、线程、子系统执行错误导致的故障
