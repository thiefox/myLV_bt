import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(receiver : str, title : str, content : str) -> bool:
    # QQ邮箱的SMTP服务器地址和端口
    SMTP_SERVER = 'smtp.qq.com'
    SMTP_PORT = 465
    # QQ邮箱的账号和授权码
    SENDER_EMAIL = '1239329163@qq.com'
    SENDER_AUTH_CODE = 'jahyinsqpyvegbfh'    # 授权码，非密码

    # 创建MIMEMultipart对象
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = receiver
    msg['Subject'] = title

    # 添加邮件正文
    msg.attach(MIMEText(content, 'plain'))

    success = False
    server = None
    try:
        # 连接到SMTP服务器
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SENDER_EMAIL, SENDER_AUTH_CODE)
        server.sendmail(SENDER_EMAIL, receiver, msg.as_string())
        success = True
    except Exception as e:
        print('发送邮件失败，原因={}'.format(e))
        pass
    finally:
        try :
            if server:
                # 关闭SMTP服务器连接
                server.quit()
        except Exception as e:
            print('关闭SMTP服务器连接失败，原因={}'.format(e))
            pass
    return success

def test():
    #receiver = 'thiefox@gmail.com'
    receiver = 'thiefox@qq.com'
    title = '测试邮件'
    content = '这是一封测试邮件'
    if send_email(receiver, title, content) :
        print('邮件发送成功')
    return

#test()