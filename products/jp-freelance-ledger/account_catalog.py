from __future__ import annotations

BOOK_GUIDE = [
 {"book":"現金出納帳","purpose":"事業用現金の入出金を取引順に記録","keywords":["現金","レジ","手渡し","現金売上","現金仕入"]},
 {"book":"売掛帳","purpose":"得意先別の掛売り・売掛金回収を記録","keywords":["請求","売掛","未入金","取引先から入金"]},
 {"book":"買掛帳","purpose":"仕入先別の掛買い・買掛金支払を記録","keywords":["仕入","買掛","後払い","仕入先"]},
 {"book":"経費帳","purpose":"仕入以外の必要経費を科目別に記録","keywords":["経費","家賃","通信","交通","広告","保険","消耗品"]},
 {"book":"固定資産台帳","purpose":"減価償却資産・繰延資産の取得、異動、償却を資産別に記録","keywords":["パソコン","車","設備","機械","固定資産","減価償却"]},
 {"book":"仕訳帳","purpose":"正規の簿記で全取引を借方・貸方に仕訳","keywords":["複式","借方","貸方","青色55万円","青色65万円"]},
 {"book":"総勘定元帳","purpose":"勘定科目別に全取引を分類・集計","keywords":["元帳","勘定科目","残高","試算表"]},
]

ACCOUNT_CATALOG = [
 {"code":"1000","name":"現金","type":"資産","audience":"common","books":["現金出納帳","仕訳帳","総勘定元帳"],"use":"事業用の現金残高。現金で売上を受け取った、現金で経費を支払ったとき。","keywords":["現金","レジ","手渡し"],"example":"現金売上: 借方 現金 / 貸方 売上高"},
 {"code":"1100","name":"普通預金","type":"資産","audience":"common","books":["預金出納帳","仕訳帳","総勘定元帳"],"use":"事業用銀行口座の入出金。","keywords":["銀行","口座","振込","入金","引落"],"example":"売掛金回収: 借方 普通預金 / 貸方 売掛金"},
 {"code":"1200","name":"売掛金","type":"資産","audience":"common","books":["売掛帳","仕訳帳","総勘定元帳"],"use":"売上済みだがまだ回収していない代金。","keywords":["請求書","未入金","掛売","後日入金"],"example":"請求時: 借方 売掛金 / 貸方 売上高"},
 {"code":"1210","name":"未収入金","type":"資産","audience":"common","books":["債権債務等記入帳","仕訳帳","総勘定元帳"],"use":"本来の営業売上以外で、まだ受け取っていない金額。","keywords":["未収","補助金未収","資産売却未収"],"example":"営業外の未収金に使用"},
 {"code":"1220","name":"立替金","type":"資産","audience":"common","books":["仕訳帳","総勘定元帳"],"use":"取引先や従業員などが負担すべき金額を一時的に立て替えたとき。","keywords":["立替","代払い"],"example":"借方 立替金 / 貸方 現金・普通預金"},
 {"code":"1240","name":"前払費用","type":"資産","audience":"common","books":["仕訳帳","総勘定元帳"],"use":"翌期以降のサービス分まで先に支払った家賃・保険・利用料など。","keywords":["前払い","年払い","翌年分","保険料"],"example":"期間配分が必要な前払い"},
 {"code":"1300","name":"棚卸資産","type":"資産","audience":"business","books":["商品有高帳","仕訳帳","総勘定元帳"],"use":"販売目的の商品・材料などの期末在庫。","keywords":["在庫","棚卸","商品","材料"],"example":"期末棚卸の集計"},
 {"code":"1510","name":"建物","type":"資産","audience":"asset","books":["固定資産台帳","仕訳帳","総勘定元帳"],"use":"事業用建物。取得価額・供用開始日・耐用年数・償却方法を管理。","keywords":["建物","店舗","事務所建物"],"example":"固定資産台帳で減価償却"},
 {"code":"1520","name":"建物附属設備","type":"資産","audience":"asset","books":["固定資産台帳","仕訳帳","総勘定元帳"],"use":"電気設備、給排水設備、内装設備など。取得時期により償却方法制限あり。","keywords":["内装","電気設備","空調","給排水"],"example":"固定資産として個別管理"},
 {"code":"1540","name":"機械装置","type":"資産","audience":"asset","books":["固定資産台帳","仕訳帳","総勘定元帳"],"use":"事業用の機械・装置。","keywords":["機械","製造設備","装置"],"example":"取得→供用→減価償却"},
 {"code":"1550","name":"車両運搬具","type":"資産","audience":"asset","books":["固定資産台帳","仕訳帳","総勘定元帳"],"use":"事業用の自動車等。家事按分が必要になることがある。","keywords":["車","自動車","バイク","車両"],"example":"固定資産台帳＋事業使用割合"},
 {"code":"1560","name":"工具器具備品","type":"資産","audience":"asset","books":["固定資産台帳","仕訳帳","総勘定元帳"],"use":"PC、机、カメラなど長期使用する備品。金額・耐用年数・特例を確認。","keywords":["パソコン","pc","カメラ","机","椅子","備品"],"example":"少額なら消耗品費候補も比較"},
 {"code":"1570","name":"ソフトウェア","type":"資産","audience":"asset","books":["固定資産台帳","仕訳帳","総勘定元帳"],"use":"取得したソフトウェア等で資産計上が必要なもの。","keywords":["ソフトウェア","システム開発","買切りソフト"],"example":"利用料はソフトウェア利用料との区別"},
 {"code":"1590","name":"減価償却累計額","type":"資産控除","audience":"advanced","books":["固定資産台帳","総勘定元帳"],"use":"固定資産の過年度減価償却累計を管理。","keywords":["累計額","減価償却累計"],"example":"間接法で固定資産残高を表示"},
 {"code":"2000","name":"買掛金","type":"負債","audience":"common","books":["買掛帳","仕訳帳","総勘定元帳"],"use":"仕入済みだがまだ支払っていない代金。","keywords":["仕入","未払","掛買"],"example":"仕入時: 借方 仕入高 / 貸方 買掛金"},
 {"code":"2010","name":"未払金","type":"負債","audience":"common","books":["債権債務等記入帳","仕訳帳","総勘定元帳"],"use":"仕入以外の物品・サービスでまだ支払っていない金額。","keywords":["未払","後払い","クレジット未払"],"example":"備品購入の後払いなど"},
 {"code":"2020","name":"未払費用","type":"負債","audience":"advanced","books":["仕訳帳","総勘定元帳"],"use":"当期に発生済みだが請求・支払が翌期になる継続的費用。","keywords":["未払費用","経過勘定","締め"],"example":"当期費用を見越計上"},
 {"code":"2030","name":"預り金","type":"負債","audience":"common","books":["仕訳帳","総勘定元帳"],"use":"源泉所得税など一時的に預かって後で納付・返還する金額。","keywords":["源泉","預り","天引き"],"example":"給与等からの預り"},
 {"code":"2050","name":"前受金","type":"負債","audience":"common","books":["仕訳帳","総勘定元帳"],"use":"まだ提供していない商品・サービス代を先に受け取ったとき。","keywords":["前受","前金","着手金"],"example":"サービス提供前の受領"},
 {"code":"2110","name":"未払消費税等","type":"負債","audience":"tax","books":["仕訳帳","総勘定元帳"],"use":"消費税の納付見込額等を処理する場合。経理方式・課税区分で扱いが変わる。","keywords":["消費税","未払消費税","納税"],"example":"税抜経理等で要確認"},
 {"code":"2150","name":"資産除去債務","type":"負債","audience":"advanced","books":["仕訳帳","総勘定元帳"],"use":"将来の除去義務を現在価値等で認識する高度な会計処理。一般的な個人事業の標準科目ではないため専門家確認を推奨。","keywords":["資産除去","原状回復","撤去義務","ARO"],"example":"上級会計。自動税務処理しない"},
 {"code":"3000","name":"元入金","type":"純資産","audience":"common","books":["仕訳帳","総勘定元帳"],"use":"個人事業の事業元本。","keywords":["元入金","開業資金"],"example":"個人事業の純資産側"},
 {"code":"3010","name":"事業主貸","type":"純資産","audience":"common","books":["仕訳帳","総勘定元帳"],"use":"事業のお金を生活費など私用に使ったとき。","keywords":["生活費","私用","個人利用","引出"],"example":"借方 事業主貸 / 貸方 現金・預金"},
 {"code":"3020","name":"事業主借","type":"純資産","audience":"common","books":["仕訳帳","総勘定元帳"],"use":"個人のお金で事業経費を払った、個人資金を事業へ入れたとき。","keywords":["個人カード","個人のお金","立替自腹"],"example":"借方 経費 / 貸方 事業主借"},
 {"code":"4000","name":"売上高","type":"収益","audience":"common","books":["売掛帳","現金出納帳","仕訳帳","総勘定元帳"],"use":"本業の商品販売・サービス提供による収入。","keywords":["売上","報酬","制作料","サービス料"],"example":"現金/預金/売掛金との相手仕訳"},
 {"code":"4030","name":"雑収入","type":"収益","audience":"common","books":["仕訳帳","総勘定元帳"],"use":"本業以外の少額・臨時収入。","keywords":["雑収入","臨時収入"],"example":"本業売上と区別"},
 {"code":"5000","name":"仕入高","type":"費用","audience":"common","books":["買掛帳","現金出納帳","仕訳帳","総勘定元帳"],"use":"販売する商品・材料等の仕入。","keywords":["仕入","商品購入","材料"],"example":"消耗品費と混同しない"},
 {"code":"5100","name":"外注工賃","type":"費用","audience":"common","books":["経費帳","仕訳帳","総勘定元帳"],"use":"外部の事業者へ業務を委託した費用。","keywords":["外注","業務委託","請負","フリーランサー"],"example":"給与賃金と区別"},
 {"code":"5110","name":"給料賃金","type":"費用","audience":"common","books":["経費帳","仕訳帳","総勘定元帳"],"use":"従業員への給与・賃金。","keywords":["給与","賃金","アルバイト"],"example":"源泉・預り金等と連動する場合あり"},
 {"code":"5200","name":"地代家賃","type":"費用","audience":"common","books":["経費帳","仕訳帳","総勘定元帳"],"use":"事務所・店舗・駐車場等の賃料。自宅兼用は家事按分を確認。","keywords":["家賃","賃料","事務所","店舗","駐車場"],"example":"借方 地代家賃 / 貸方 現金・預金"},
 {"code":"5210","name":"水道光熱費","type":"費用","audience":"common","books":["経費帳","仕訳帳","総勘定元帳"],"use":"事業用の電気・ガス・水道。自宅兼用は按分を確認。","keywords":["電気","ガス","水道","光熱"],"example":"家事按分候補"},
 {"code":"5220","name":"広告宣伝費","type":"費用","audience":"common","books":["経費帳","仕訳帳","総勘定元帳"],"use":"広告、チラシ、Web広告など販売促進費。","keywords":["広告","google ads","meta ads","チラシ","宣伝"],"example":"販売促進目的"},
 {"code":"5230","name":"接待交際費","type":"費用","audience":"review","books":["経費帳","仕訳帳","総勘定元帳"],"use":"事業関係者との接待・贈答等。事業関連性を記録。","keywords":["接待","会食","贈答","手土産"],"example":"相手・目的メモを残す"},
 {"code":"5240","name":"損害保険料","type":"費用","audience":"common","books":["経費帳","仕訳帳","総勘定元帳"],"use":"事業用資産・業務に関する損害保険料。","keywords":["保険","火災保険","賠償保険"],"example":"私用分との区分確認"},
 {"code":"5250","name":"修繕費","type":"費用","audience":"review","books":["経費帳","仕訳帳","総勘定元帳"],"use":"原状回復・維持管理の修理。資本的支出に該当する場合は固定資産との区別が必要。","keywords":["修理","修繕","交換","補修"],"example":"価値増加・耐用年数延長なら資産計上検討"},
 {"code":"5260","name":"租税公課","type":"費用","audience":"review","books":["経費帳","仕訳帳","総勘定元帳"],"use":"事業に関係する一定の税・公的負担。所得税等は必要経費にならないため要確認。","keywords":["印紙","事業税","固定資産税","税金"],"example":"税目ごとに必要経費性を確認"},
 {"code":"5270","name":"支払手数料","type":"費用","audience":"common","books":["経費帳","仕訳帳","総勘定元帳"],"use":"振込、決済、プラットフォーム等の手数料。","keywords":["振込手数料","決済手数料","stripe","paypal","販売手数料"],"example":"売上総額とのネット計上に注意"},
 {"code":"5300","name":"通信費","type":"費用","audience":"common","books":["経費帳","仕訳帳","総勘定元帳"],"use":"電話、携帯、インターネット、郵便等。","keywords":["携帯","スマホ","電話","wifi","internet","回線","郵便"],"example":"家事按分候補"},
 {"code":"5320","name":"車両費","type":"費用","audience":"review","books":["経費帳","仕訳帳","総勘定元帳"],"use":"事業用車両の燃料・駐車場・高速代等。資産取得や減価償却とは別。","keywords":["ガソリン","駐車場","高速","車検","車両"],"example":"事業使用割合を確認"},
 {"code":"5340","name":"ソフトウェア利用料","type":"費用","audience":"common","books":["経費帳","仕訳帳","総勘定元帳"],"use":"SaaSや月額ソフト等の利用料。買切り・開発費は資産計上との区別が必要。","keywords":["saas","subscription","月額","adobe","office","github"],"example":"継続利用料"},
 {"code":"5400","name":"旅費交通費","type":"費用","audience":"common","books":["経費帳","仕訳帳","総勘定元帳"],"use":"事業上の電車・バス・タクシー・出張交通費等。","keywords":["電車","バス","タクシー","新幹線","航空券","出張"],"example":"出張目的を摘要に残す"},
 {"code":"5500","name":"消耗品費","type":"費用","audience":"common","books":["経費帳","仕訳帳","総勘定元帳"],"use":"事務用品や少額備品等。高額・長期使用は固定資産との区別が必要。","keywords":["文具","インク","ケーブル","少額備品","amazon","ホームセンター"],"example":"PC等は金額・耐用年数で固定資産候補"},
 {"code":"5600","name":"減価償却費","type":"費用","audience":"asset","books":["固定資産台帳","経費帳","仕訳帳","総勘定元帳"],"use":"固定資産の取得価額を耐用年数に応じて費用配分。","keywords":["減価償却","固定資産","耐用年数"],"example":"固定資産台帳から自動計算"},
 {"code":"5900","name":"雑費","type":"費用","audience":"common","books":["経費帳","仕訳帳","総勘定元帳"],"use":"他の適切な科目に当てはまらない少額・臨時の必要経費。多用は避ける。","keywords":["雑費","その他"],"example":"より具体的な科目があればそちらを優先"},
]

def search_catalog(query, limit=8, audience=None):
    q=(query or "").strip().lower()
    if not q:return []
    scored=[]
    for item in ACCOUNT_CATALOG:
        if audience and item.get("audience") not in audience:continue
        hay=" ".join([item["name"],item["type"],item["use"],item["example"]," ".join(item["keywords"])," ".join(item["books"])]).lower()
        score=0
        if q==item["name"].lower():score+=20
        if q in item["name"].lower():score+=10
        if q in hay:score+=4
        for token in q.replace("　"," ").split():
            if token and token in hay:score+=2
        if score:scored.append((score,item))
    scored.sort(key=lambda x:(-x[0],x[1]["code"]))
    return [dict(item,score=score) for score,item in scored[:max(1,int(limit))]]

def search_books(query,limit=5):
    q=(query or "").strip().lower()
    if not q:return []
    out=[]
    for b in BOOK_GUIDE:
        hay=(b["book"]+" "+b["purpose"]+" "+" ".join(b["keywords"])).lower()
        score=(10 if q in b["book"].lower() else 0)+(4 if q in hay else 0)+sum(2 for t in q.split() if t in hay)
        if score:out.append((score,b))
    out.sort(key=lambda x:-x[0])
    return [dict(x[1],score=x[0]) for x in out[:limit]]
