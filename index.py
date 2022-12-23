import evd

application = evd.server

def run_display(host, port):
    """
    Call main app run display
    """
    evd.run_display(host, port)

    return application

if __name__ == '__main__':
    application.run()