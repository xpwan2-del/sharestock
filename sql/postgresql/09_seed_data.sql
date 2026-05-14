-- ============================================================
-- PostgreSQL DDL: 产业链初始化数据
-- 从 INDUSTRY_CHAIN_MAP 硬编码导入
-- ============================================================

-- 八大产业链
INSERT INTO quant.industry_chain_def (chain_name, chain_desc) VALUES
('新能源汽车', '锂矿-动力电池-整车-充电桩全产业链'),
('光伏', '硅料-硅片-电池片-组件-电站全产业链'),
('半导体', 'EDA-设计-制造-封测全产业链'),
('人工智能', '算力-大模型-AI应用全产业链'),
('医药医疗', '原料药-CXO-创新药-医疗器械全产业链'),
('机器人', '减速器-伺服-本体-应用全产业链'),
('低空经济', '碳纤维-飞控-eVTOL-低空应用全产业链'),
('消费电子', '芯片-面板-模组-终端品牌全链路');

-- 环节定义（upstream/midstream/downstream）
DO $$
DECLARE
    chain_rec RECORD;
BEGIN
    FOR chain_rec IN SELECT id, chain_name FROM quant.industry_chain_def LOOP
        INSERT INTO quant.chain_segment (chain_id, segment_name, sort_order) VALUES
        (chain_rec.id, '上游', 1),
        (chain_rec.id, '中游', 2),
        (chain_rec.id, '下游', 3);
    END LOOP;
END $$;

-- 细分行业（示例：新能源汽车产业链）
INSERT INTO quant.chain_sub_industry (segment_id, sub_name)
SELECT s.id, v.sub_name
FROM quant.chain_segment s
JOIN quant.industry_chain_def c ON s.chain_id = c.id
CROSS JOIN LATERAL (
    VALUES
        -- 新能源汽车
        ('锂矿'), ('钴矿'), ('镍矿'), ('稀土永磁'), ('石墨负极'),
        ('电解液'), ('隔膜'), ('正极材料'), ('动力电池'), ('电机电控'),
        ('热管理'), ('轻量化'), ('汽车电子'), ('IGBT'),
        ('整车制造'), ('充电桩'), ('换电'), ('汽车后市场'),

        -- 光伏
        ('硅料'), ('硅片'), ('光伏银浆'), ('光伏玻璃'), ('胶膜'),
        ('电池片'), ('组件'), ('逆变器'), ('支架'), ('金刚线'),
        ('电站运营'), ('储能'), ('BIPV'),

        -- 半导体
        ('EDA软件'), ('IP核'), ('半导体设备'), ('光刻胶'), ('特种气体'), ('靶材'),
        ('芯片设计'), ('晶圆代工'), ('封装测试'),
        ('消费电子'), ('工业控制'), ('数据中心'), ('通信设备'),

        -- 人工智能
        ('算力芯片GPU'), ('光模块'), ('服务器'), ('数据标注'),
        ('大模型'), ('AI应用开发'), ('机器视觉'), ('NLP'), ('智能语音'),
        ('智能驾驶'), ('智能家居'), ('工业AI'), ('医疗AI'), ('金融AI'),

        -- 医药医疗
        ('原料药'), ('中间体'), ('CXO'), ('生命科学服务'), ('医疗设备零部件'),
        ('创新药'), ('仿制药'), ('医疗器械'), ('IVD体外诊断'), ('疫苗'),
        ('医院'), ('连锁药房'), ('互联网医疗'), ('医美'),

        -- 机器人
        ('减速器'), ('伺服电机'), ('控制器'), ('传感器'), ('丝杠'),
        ('工业机器人本体'), ('人形机器人'), ('协作机器人'), ('AGV/AMR'),
        ('汽车制造'), ('3C电子'), ('金属加工'), ('物流仓储'), ('医疗服务'),

        -- 低空经济
        ('碳纤维'), ('航空发动机'), ('飞控系统'), ('导航系统'), ('复合材料'),
        ('eVTOL制造'), ('无人机'), ('通用航空器'), ('飞行汽车'),
        ('低空物流'), ('低空旅游'), ('应急救援'), ('农业植保'), ('城市空中交通'),

        -- 消费电子
        ('芯片'), ('面板'), ('结构件'), ('PCB'), ('电池'), ('声学部件'), ('光学镜头'),
        ('手机制造'), ('PC制造'), ('可穿戴设备'), ('VR/AR'), ('智能音箱'),
        ('品牌商'), ('渠道'), ('回收')
) AS v(sub_name)
-- 按产业链名和环节匹配（简化逻辑：按位置推断上下游）
WHERE
    (c.chain_name = '新能源汽车' AND (
        (s.segment_name = '上游' AND v.sub_name IN ('锂矿','钴矿','镍矿','稀土永磁','石墨负极','电解液','隔膜','正极材料')) OR
        (s.segment_name = '中游' AND v.sub_name IN ('动力电池','电机电控','热管理','轻量化','汽车电子','IGBT')) OR
        (s.segment_name = '下游' AND v.sub_name IN ('整车制造','充电桩','换电','汽车后市场'))
    )) OR
    (c.chain_name = '光伏' AND (
        (s.segment_name = '上游' AND v.sub_name IN ('硅料','硅片','光伏银浆','光伏玻璃','胶膜')) OR
        (s.segment_name = '中游' AND v.sub_name IN ('电池片','组件','逆变器','支架','金刚线')) OR
        (s.segment_name = '下游' AND v.sub_name IN ('电站运营','储能','BIPV'))
    )) OR
    (c.chain_name = '半导体' AND (
        (s.segment_name = '上游' AND v.sub_name IN ('EDA软件','IP核','半导体设备','硅片','光刻胶','特种气体','靶材')) OR
        (s.segment_name = '中游' AND v.sub_name IN ('芯片设计','晶圆代工','封装测试')) OR
        (s.segment_name = '下游' AND v.sub_name IN ('消费电子','汽车电子','工业控制','数据中心','通信设备'))
    )) OR
    (c.chain_name = '人工智能' AND (
        (s.segment_name = '上游' AND v.sub_name IN ('算力芯片GPU','光模块','服务器','数据中心','数据标注')) OR
        (s.segment_name = '中游' AND v.sub_name IN ('大模型','AI应用开发','机器视觉','NLP','智能语音')) OR
        (s.segment_name = '下游' AND v.sub_name IN ('智能驾驶','智能家居','工业AI','医疗AI','金融AI'))
    )) OR
    (c.chain_name = '医药医疗' AND (
        (s.segment_name = '上游' AND v.sub_name IN ('原料药','中间体','CXO','生命科学服务','医疗设备零部件')) OR
        (s.segment_name = '中游' AND v.sub_name IN ('创新药','仿制药','医疗器械','IVD体外诊断','疫苗')) OR
        (s.segment_name = '下游' AND v.sub_name IN ('医院','连锁药房','互联网医疗','医美'))
    )) OR
    (c.chain_name = '机器人' AND (
        (s.segment_name = '上游' AND v.sub_name IN ('减速器','伺服电机','控制器','传感器','丝杠')) OR
        (s.segment_name = '中游' AND v.sub_name IN ('工业机器人本体','人形机器人','协作机器人','AGV/AMR')) OR
        (s.segment_name = '下游' AND v.sub_name IN ('汽车制造','3C电子','金属加工','物流仓储','医疗服务'))
    )) OR
    (c.chain_name = '低空经济' AND (
        (s.segment_name = '上游' AND v.sub_name IN ('碳纤维','航空发动机','飞控系统','导航系统','复合材料')) OR
        (s.segment_name = '中游' AND v.sub_name IN ('eVTOL制造','无人机','通用航空器','飞行汽车')) OR
        (s.segment_name = '下游' AND v.sub_name IN ('低空物流','低空旅游','应急救援','农业植保','城市空中交通'))
    )) OR
    (c.chain_name = '消费电子' AND (
        (s.segment_name = '上游' AND v.sub_name IN ('芯片','面板','结构件','PCB','电池','声学部件','光学镜头')) OR
        (s.segment_name = '中游' AND v.sub_name IN ('手机制造','PC制造','可穿戴设备','VR/AR','智能音箱')) OR
        (s.segment_name = '下游' AND v.sub_name IN ('品牌商','渠道','回收'))
    ))
ON CONFLICT (segment_id, sub_name) DO NOTHING;