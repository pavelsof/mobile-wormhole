import json
import os

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.protocols.basic import FileSender
from wormhole import create
from wormhole.cli.cmd_send import APPID
from wormhole.cli.public_relay import RENDEZVOUS_RELAY, TRANSIT_RELAY
from wormhole.transit import TransitSender


class Wormhole:

    def __init__(self):
        """
        Create a magic wormhole.
        """
        self.wormhole = create(APPID, RENDEZVOUS_RELAY, reactor)
        self.transit = None

    def generate_code(self):
        """
        Generate the code that the users at the two ends of the wormhole will
        have to exchange.

        Return a Deferred that resolves into the code or rejects with Timeout.
        """
        self.wormhole.allocate_code()
        deferred = self.wormhole.get_code()
        return deferred

    def exchange_keys(self):
        """
        Return a Deferred that resolves when the key exchange between the two
        clients has been completed.

        The Deferred resolves into the so-called verifier, a hash of the shared
        key, which can be compared by the users at both ends of the wormhole in
        order to make sure no man-in-the-middle attack is taking place.

        The Deferred can reject with WrongPasswordError or Timeout.
        """
        deferred = self.wormhole.get_verifier()
        return deferred

    def send_json(self, message):
        """
        Send a JSON message down the wormhole.
        """
        self.wormhole.send_message(bytes(json.dumps(message), 'utf-8'))

    @inlineCallbacks
    def await_json(self):
        """
        Return a Deferred that resolves into the next JSON message that comes
        out of the wormhole.
        """
        message = yield self.wormhole.get_message()
        return json.loads(str(message, 'utf-8'))

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
