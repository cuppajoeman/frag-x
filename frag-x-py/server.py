import socket
import pickle
import _thread
import sys 
import pygame
from typing import List
from game_engine_constants import SCREEN_CENTER_POINT, ORIGIN, BUF_SIZE, PORT, LOCAL_IP, SERVER_TICK_RATE_HZ, REMOTE_IP
from network import FragNetwork
from converters import str_to_player_data
from player import ServerPlayer
from threading import Lock, Thread
from queue import Queue

#SERVER_ADDRESS = LOCAL_IP
SERVER_ADDRESS = REMOTE_IP

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try: 
    s.bind((SERVER_ADDRESS, PORT))

except socket.error as e:
    str(e)

s.listen(2)

print(f"Server started on {(SERVER_ADDRESS, PORT)}")

players = []

player_start_positions = [ORIGIN, SCREEN_CENTER_POINT]

def client_state_producer(conn, state_queue):
    """
    This function gets run as a thread, it is associated with a single player and retreives their inputs
    """
    # This sends the initial position of the player
    # conn.send(str.encode(convert_pos_int_repr_to_str_repr(player_start_positions[player_id])))

    #p = ServerPlayer(player_start_positions[player_id], 50, 50)

    #players.append(p)

    reply = ""
    iterations = 0
    recv_buffer = ""
    while True:
        try: 
            data = conn.recv(BUF_SIZE)

            if not data:
                # Likely means we've disconnected
                break
            else:
                print(f'Received: {data.decode("utf-8")}')

                recv_buffer += data.decode("utf-8")

                messages = recv_buffer.split('~')

                recv_buffer = messages[-1]

                for player_data in messages[:-1]:

                    q_drain_lock.acquire()

                    state_queue.put(str_to_player_data(player_data))

                    q_drain_lock.release()

        except Exception as e:
            print(f"wasn't able to get data because {e}")
            break
        iterations += 1

    print("Lost connection")
    conn.close()

id_to_player = {}

def threaded_server_acceptor(state_queue):
    # Allowing this because it's not being accessed anywhere else
    player_id = 0
    # CONNECT LOOP
    while True:
        conn, addr = s.accept()
        conn.send(str.encode(str(player_id)))
        print(f"Accept connection from {addr}")

        player_lock.acquire()

        id_to_player[player_id] = ServerPlayer((0,0), 50, 50, player_id, conn)

        player_lock.release()

        # If a player connects they get their own thread
        t = Thread(target=client_state_producer, args=(conn, state_queue))
        t.start()
        
        player_id += 1


# for batching the inputs and running physics simulation

q_drain_lock = Lock()
player_lock = Lock()
clock = pygame.time.Clock()     ## For syncing the FPS
state_queue = Queue()
server_updates = []

tsa_t = Thread(target=threaded_server_acceptor, args=(state_queue,))
tsa_t.start()


while True:

    clock.tick(SERVER_TICK_RATE_HZ)     ## will make the loop run at the same speed all the time

    q_drain_lock.acquire()  

    while not state_queue.empty():
        print("q is drainable")
        player_id, dx, dy, dm, delta_time = state_queue.get()

        if player_id in id_to_player:
            p = id_to_player[player_id]
            p.update_position(dx, dy, delta_time)
            p.update_aim(dm)
    
    q_drain_lock.release()  

    player_lock.acquire()

    # get the game state ready to be sent
    for p in id_to_player.values():
        server_updates.append(p.get_sendable_state())

    # Send the game state to each of the players
    for p in id_to_player.values():
        print("server updates", server_updates)
        p.socket.sendall(pickle.dumps(server_updates))

    # reset server updates
    server_updates = []

    player_lock.release()

