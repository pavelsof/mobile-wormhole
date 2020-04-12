import json
import os

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, TimeoutError
from twisted.protocols.basic import FileSender
from wormhole import create
from wormhole.cli.cmd_send import APPID
from wormhole.cli.public_relay import RENDEZVOUS_RELAY, TRANSIT_RELAY
from wormhole.errors import WrongPasswordError
from wormhole.transit import TransitSender


class HumanError(Exception):
    """
    Raised when one of the humans at either end of the wormhole does something
    that breaks it, e.g. enters the wrong code.
    """
    pass


class SuspiciousOperation(Exception):
    """
    Raised when things do not go according to the protocol, e.g. a message that
    cannot be parsed is received.
    """
    pass


class Timeout(Exception):
    """
    Raised when the rendezvous server or the other end of the wormhole take
    longer than expected to respond.
    """
    pass


class Wormhole:

    def __init__(
            self, app_id=APPID, rendezvous_relay=RENDEZVOUS_RELAY,
            transit_relay=TRANSIT_RELAY
        ):
        """
        Create a magic wormhole.
        """
        self.app_id = app_id
        self.rendezvous_relay = rendezvous_relay
        self.transit_relay = transit_relay

        self.wormhole = create(self.app_id, self.rendezvous_relay, reactor)
        self.transit = None

    @inlineCallbacks
    def generate_code(self, timeout=10):
        """
        Generate the code that the users at the two ends of the wormhole will
        have to exchange.

        Return a Deferred that resolves into the code.
        """
        self.wormhole.allocate_code()

        deferred = self.wormhole.get_code()
        deferred.addTimeout(timeout, reactor)

        try:
            code = yield deferred
        except TimeoutError:
            raise Timeout('could not connect to the server')

        return returnValue(code)

    @inlineCallbacks
    def connect(self, code, timeout=10):
        """
        Connect to another wormhole client by its code generated. This has to
        be exchanged between the two users before the wormhole connects.

        Return a Deferred that resolves upon successful connection.
        """
        self.wormhole.set_code(code)

        deferred = self.wormhole.get_code()
        deferred.addTimeout(timeout, reactor)

        try:
            yield deferred
        except TimeoutError:
            raise Timeout('could not connect to the other end')

    @inlineCallbacks
    def exchange_keys(self, timeout=10):
        """
        Return a Deferred that resolves when the key exchange between the two
        clients has been completed.

        The Deferred resolves into the so-called verifier, a hash of the shared
        key, which can be compared by the users at both ends of the wormhole in
        order to make sure no man-in-the-middle attack is taking place.
        """
        deferred = self.wormhole.get_verifier()
        deferred.addTimeout(timeout, reactor)

        try:
            verifier = yield deferred
        except TimeoutError:
            raise Timeout('could not exchange keys with the other end')
        except WrongPasswordError:
            raise HumanError('the other end entered a wrong code')

        return returnValue(verifier)

    def send_json(self, message):
        """
        Send a JSON message down the wormhole.
        """
        self.wormhole.send_message(bytes(json.dumps(message), 'utf-8'))

    @inlineCallbacks
    def await_json(self, timeout=10):
        """
        Return a Deferred that resolves into the next JSON message that comes
        out of the wormhole.
        """
        deferred = self.wormhole.get_message()
        deferred.addTimeout(timeout, reactor)

        try:
            message = yield deferred
            message = json.loads(str(message, 'utf-8'))
        except TimeoutError:
            raise Timeout('no message came from the other side')
        except:
            raise SuspiciousOperation('bad message came from the other side')

        return returnValue(message)

    @inlineCallbacks
    def establish_transit(self):
        """
        """
        self.transit = TransitSender(TRANSIT_RELAY)
        our_hints = yield self.transit.get_connection_hints()

        self.send_json({
            'transit': {
                'abilities-v1': self.transit.get_connection_abilities(),
                'hints-v1': our_hints,
            }
        })

        response = yield self.await_json()
        self.transit.add_connection_hints(response['transit']['hints-v1'])

        transit_key = self.wormhole.derive_key(
            '{}/transit-key'.format(APPID), self.transit.TRANSIT_KEY_LENGTH
        )
        self.transit.set_transit_key(transit_key)

    @inlineCallbacks
    def send_file(self, file_path):
        """
        Send a file down the wormhole.

        The Deferred can reject with TransitError or Timeout.
        """
        if not self.transit:
            yield self.establish_transit()

        record_pipe = yield self.transit.connect()

        self.send_json({
            'offer': {
                'file': {
                    'filename': os.path.basename(file_path),
                    'filesize': os.stat(file_path).st_size
                }
            }
        })

        response = yield self.await_json()

        try:
            assert response['answer']['file_ack'] == 'ok'
        except (AssertionError, KeyError):
            raise

        with open(file_path, 'rb') as f:
            file_sender = FileSender()
            yield file_sender.beginFileTransfer(f, record_pipe)

        ack_record = yield record_pipe.receive_record()
        ack_record = json.loads(str(ack_record, 'utf-8'))

        record_pipe.close()

    @inlineCallbacks
    def await_offer(self):
        """
        Return a Deferred that resolves into a {filename, filesize} dict a
        file offer is received from the other end of the wormhole.

        The Deferred can reject with Timeout.

        This method should be called by the receiving end of the wormhole.
        """
        offer = yield self.await_json()
        print(offer)

    @inlineCallbacks
    def accept_offer(self, path):
        """
        Download the file offered to be sent by the other end of the wormhole.

        This method should be called by the receiving end of the wormhole.
        """
        pass

    def close(self):
        """
        Close the wormhole.

        Return a Deferred that resolves into the string "happy" when done or
        rejects with one of the following errors: WelcomeError, ServerError,
        LonelyError, WrongPasswordError [1].

        [1]: https://magic-wormhole.readthedocs.io/en/latest/api.html#closing
        """
        deferred = self.wormhole.close()
        return deferred
